"""Research-only Light HQ-SAM box-prompt adapter; no postprocessing or truth prompts.

The upstream public predictor returns one HQ-combined mask even when its
multimask flag is True. This adapter retains all four SAM tokens, the HQ token,
and all four SAM+HQ combinations so research results cannot hide alternatives.
"""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
import subprocess
import sys
import time

import numpy as np


SOURCE_REVISION = "e696978d60352dc9a26b12631cd91781502c6546"
CHECKPOINT_REVISION = "a3a77cd0a2e5e50eaa76faccf61b964732d9b35f"
CHECKPOINT_URL = (
    "https://huggingface.co/lkeab/hq-sam/resolve/"
    f"{CHECKPOINT_REVISION}/sam_hq_vit_tiny.pth"
)
CHECKPOINT_SHA256 = "0f32c075ccdd870ae54db2f7630e7a0878ede5a2b06d05d6fe02c65a82fb7196"


def checkpoint_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LightHQSamAdapter:
    """Load a pinned upstream checkout and checkpoint in a research environment.

    Each ``predict`` call encodes the supplied RGB image anew. Thus a moving
    occluder changes the image features; cached old-image features are not used.
    The caller supplies only the locator box, in the supplied image's pixels.
    """

    def __init__(self, source_dir: str | Path, checkpoint: str | Path,
                 device: str = "cpu") -> None:
        source_dir = Path(source_dir).resolve()
        checkpoint = Path(checkpoint).resolve()
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=source_dir, text=True
        ).strip()
        if revision != SOURCE_REVISION:
            raise ValueError(f"Expected source {SOURCE_REVISION}, found {revision}")
        digest = checkpoint_sha256(checkpoint)
        if digest != CHECKPOINT_SHA256:
            raise ValueError(f"Unexpected checkpoint SHA256: {digest}")

        sys.path.insert(0, str(source_dir))
        torch = importlib.import_module("torch")
        upstream = importlib.import_module("segment_anything")
        if not Path(upstream.__file__).resolve().is_relative_to(source_dir):
            raise RuntimeError("Another segment_anything package was already imported")
        self.torch = torch
        self.device = torch.device(device)
        self.model = upstream.sam_model_registry["vit_tiny"](checkpoint=None)
        state = torch.load(checkpoint, map_location="cpu", weights_only=True)
        incompatible = self.model.load_state_dict(state, strict=False)
        unused_classifier = ("image_encoder.head.", "image_encoder.norm_head.")
        missing_used = [key for key in incompatible.missing_keys
                        if not key.startswith(unused_classifier)]
        if missing_used:
            raise RuntimeError(f"Missing inference weights: {missing_used}")
        self.load_info = {
            "missing_keys": list(incompatible.missing_keys),
            "unexpected_keys": list(incompatible.unexpected_keys),
        }
        # Refresh TinyViT's eval-time attention-bias cache AFTER loading weights.
        self.model.to(self.device).eval()
        self.predictor = upstream.SamPredictor(self.model)

    def _sync(self) -> None:
        if self.device.type == "cuda":
            self.torch.cuda.synchronize(self.device)

    def predict(self, rgb: np.ndarray, box_xyxy, *, verify_api: bool = False) -> dict:
        """Return all masks/logits and upstream scores from an automatic box.

        ``rgb`` must be HxWx3 uint8 RGB; a Pillow ``convert('RGB')`` result works.
        ``box_xyxy`` is [xmin,ymin,xmax,ymax] in that same image's pixels.
        Scores predict SAM-token IoU; HQ-only has NO independent quality score.
        Mask threshold is upstream's logit > 0. No holes are filled, and no
        components, hulls, morphology, or color filtering are applied.
        """
        if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError("Expected HxWx3 uint8 RGB image")
        box = np.asarray(box_xyxy, dtype=np.float32)
        if box.shape != (4,) or not np.isfinite(box).all():
            raise ValueError("Expected finite XYXY box of length four")
        h, w = rgb.shape[:2]
        if not (0 <= box[0] < box[2] <= w and 0 <= box[1] < box[3] <= h):
            raise ValueError(f"Box {box.tolist()} is outside image {(w, h)}")

        torch = self.torch
        with torch.inference_mode():
            self._sync()
            start = time.perf_counter()
            # Official PIL/torchvision ResizeLongestSide (long side 1024),
            # RGB [0,255], channel mean/std, then zero-pad right and bottom.
            self.predictor.set_image(np.ascontiguousarray(rgb), image_format="RGB")
            self._sync()
            encoded = time.perf_counter()

            transformed_box = self.predictor.transform.apply_boxes(
                box[None, :], self.predictor.original_size
            )
            sparse, dense = self.model.prompt_encoder(
                points=None,
                boxes=torch.as_tensor(transformed_box, dtype=torch.float32,
                                      device=self.device),
                masks=None,
            )
            decoder = self.model.mask_decoder
            # TinyViT: final [1,256,64,64], early HQ [1,64,64,160].
            early = self.predictor.interm_features[0].permute(0, 3, 1, 2)
            hq_features = (decoder.embedding_encoder(self.predictor.features)
                           + decoder.compress_vit_feat(early))
            raw, scores = decoder.predict_masks(
                image_embeddings=self.predictor.features,
                image_pe=self.model.prompt_encoder.get_dense_pe(),
                sparse_prompt_embeddings=sparse,
                dense_prompt_embeddings=dense,
                hq_features=hq_features,
            )
            if raw.shape[1:] != (5, 256, 256) or scores.shape != (1, 4):
                raise RuntimeError(f"Unexpected decoder shapes: {raw.shape}, {scores.shape}")
            sam_low = raw[:, :4]
            hq_low = raw[:, 4:5]
            combined_low = sam_low + hq_low

            def original_resolution(low):
                return self.model.postprocess_masks(
                    low, self.predictor.input_size, self.predictor.original_size
                )[0].cpu().numpy()

            combined = original_resolution(combined_low)
            sam = original_resolution(sam_low)
            hq = original_resolution(hq_low)[0]
            sam_scores = scores[0].cpu().numpy()
            self._sync()
            finished = time.perf_counter()

            # A fixed, observable model choice; no target-mask lookup.
            selected_multi = 1 + int(np.argmax(sam_scores[1:4]))
            if verify_api:
                for multimask, expected_index in ((False, 0), (True, selected_multi)):
                    official, official_scores, _ = self.predictor.predict(
                        box=box, multimask_output=multimask,
                        return_logits=True, hq_token_only=False,
                    )
                    np.testing.assert_allclose(official[0], combined[expected_index],
                                               rtol=1e-4, atol=1e-4)
                    np.testing.assert_allclose(official_scores[0], sam_scores[expected_index],
                                               rtol=1e-4, atol=1e-4)

        return {
            "combined_masks": combined > self.model.mask_threshold,
            "combined_logits": combined,
            "sam_masks": sam > self.model.mask_threshold,
            "sam_logits": sam,
            "hq_only_mask": hq > self.model.mask_threshold,
            "hq_only_logits": hq,
            "low_res_raw_logits": raw[0].cpu().numpy(),
            "sam_scores": sam_scores,
            "selected_box_index": 0,
            "selected_multimask_index": selected_multi,
            "timings_seconds": {
                "encode": encoded - start,
                "decode_and_postprocess": finished - encoded,
                "total": finished - start,
            },
            "feature_shapes": {
                "final": list(self.predictor.features.shape),
                "early_hq": [list(x.shape) for x in self.predictor.interm_features],
            },
            "api_verified": verify_api,
            "checkpoint_sha256": CHECKPOINT_SHA256,
            "source_revision": SOURCE_REVISION,
            "load_info": self.load_info,
        }

