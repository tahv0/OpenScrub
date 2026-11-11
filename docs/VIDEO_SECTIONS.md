# Video sections and live work progress (experimental)

Video sections let you review and approve parts of a recording independently.
You can export a finished section, then try a different learned plate model on
another interval. Each approved revision has its own saved review snapshot.
A new rescan opens a separate **section candidate**; your approval is what
replaces that interval in the parent video's results.

**Review the rendered video and audio before sharing it.** Approval records
your review decision. Detection and model validation still cannot guarantee
that every identifying detail has been found.

## Create, approve and export a section

1. Open an existing job in **Review**, **Paused** or **Done**. Save your review
   edits and wait for **Review edits saved to disk**. Let any pending corner
   autosaves finish too.
2. Open **Video sections**. Enter a name, **Start (s or mm:ss)** and **End (s or mm:ss)**,
   then choose **Add section**. Times refer to the original video. You can enter
   seconds or `mm:ss`, including fractional seconds. Sections must not overlap;
   adjacent sections can share an endpoint.
3. Review the findings, manual masks and audio decisions for that interval.
   Use the original video's preview to inspect moving objects and the section
   edges. Adding a section does not itself approve its contents.
4. Choose **Approve current results**. The section shows its approved revision
   and the model or original masks associated with it. Its saved snapshot
   includes the review geometry and export settings.
5. Choose **Export approved section**. OpenScrub opens an attached export job
   and renders the selected interval from the source. Wait for rendering to
   finish, download the result, and inspect its video and audio.

The exported video starts at playback time zero and contains only the approved
interval. Its review data continues to use original-video times. For example,
a section from `05:00` to `06:00` becomes a roughly one-minute video, while its
findings remain attached to the original recording's five-to-six-minute range.

**Open export** returns to the most recent export job. **Back to video sections**
returns to the parent video. An export job uses its saved approved revision;
use a candidate when you want to change the masks or train again.

## How time boundaries become frames

Section boundaries are stored as source-frame indices. Both entered times are
rounded upward to the first frame at or after that time. The start frame is
included and the end frame is excluded. This gives adjacent sections a precise
shared boundary without including the same frame twice.

For a 10 fps video, entering `1.01` to `2.01` seconds selects frames 11 through
20: the saved interval begins at `1.10` seconds and ends immediately before
frame 21 at `2.10` seconds. The export contains ten frames. A very short interval
whose two times round to the same frame is rejected. Displayed times may be
rounded for readability; the stored frame boundaries control the export.

Audio is trimmed to the same selected interval. Existing mute and bleep spans
are clipped and shifted to the export's local timeline, and tracks that begin
later than the video keep their timing offset. SDR and HDR section exports
honor the frame bounds. A source or decoder alignment failure stops the export
and removes incomplete output.

## Rescan a section with another model

1. In the parent video's **Video sections** panel, choose **Model for section
   rescans**. Select **Original plate masks** or a saved learned model. See
   [Reusable learned plate models](REUSABLE_MODELS.md) to save or import one.
2. Choose **Rescan section**. The new candidate is attached to the same source
   video and has its own report. The existing approved revision stays available
   while this work runs. **Open candidate** returns to it later.
3. Review the candidate's findings and disagreements. Saved manual masks and
   source-bound human decisions are carried into the candidate. Check their
   placement, especially where objects move across an edge or a new model
   changes the proposed shape. Make and save any further corrections there.
4. If you want to train from additional verified plate corners, use the
   candidate's **Train & rescan this video** action. It still requires the
   optional CUDA training setup and sufficient training and held-out examples.
   Selecting an existing saved model for a rescan runs inference; it does not
   train that model. See [Video-specific learning](VIDEO_LEARNING.md) for setup
   and the acceptance gates.
5. Choose **Approve this section** when the candidate is ready. OpenScrub saves
   a new approved revision and replaces only the selected interval in the
   parent report. Other approved sections and results outside that interval
   stay in place. Export the approved section again to obtain its updated video.

A failed, cancelled or unapproved candidate leaves the previous approved
snapshot intact. A candidate based on an older approval cannot overwrite a
newer approved revision. Changing the model selection also does not change
already approved masks. Export uses the snapshot's saved geometry and settings,
so it does not need to rerun a newer version of the model to reconstruct them.

## What approval protects

Approved section masks and audio decisions are locked against direct changes
from the parent review. Open a section candidate to revise them. Review edits
outside approved intervals remain available. Whole-job retraining, retry and
learning rollback actions that could replace approved work are blocked; use
the section workflow for those changes.

Manual masks are carried in source coordinates even if a candidate's scroll
tracking differs. Human plate corners and explicit false-positive decisions
retain the normal learning workflow's matching and conflict checks. Review the
candidate before approval; an ambiguous match or uncertain learned prediction
can still require a human correction.

Approving a replacement makes an older whole-video output out of date. Render
again before downloading a whole-video result that is meant to include the
new section. Previously saved approval snapshots are retained, while
**Export approved section** uses the current approved revision.
Approving unchanged current results keeps any existing rendered output available.

### Paused scans and detection windows

On a paused job, approval, section rescanning and export require the entire
selected interval to have been scanned. An interval that crosses the checkpoint,
an unscanned tail or a skipped gap is refused. Resume the parent scan to cover
the next portion before using it as a section. A failed attempt does not approve
or publish the missing frames.

This allows an independently reviewed, fully scanned section to be exported
while the parent recording remains paused. The whole paused recording still
cannot be rendered or downloaded as though its unscanned remainder were ready.
See [Stop & Review](STOP_REVIEW.md) for saving and continuing the parent scan.

## Read progress during learning and rescanning

The active job view shows the current stage, available work counts, elapsed
time for that stage and the age of the last reported progress. Counts have
different meanings at different stages:

| Stage | What the displayed progress means |
| --- | --- |
| Example collection | Saved training examples collected, with source-decoder position while it reaches the next required frame. Training has not started yet. |
| Training | Actual epoch and completed-batch counters from trainer callbacks. Early stopping can finish before the requested maximum epoch count. |
| Validation | Candidate validation and the later held-out coverage check. Batch counts are shown when available. |
| Export and integrity checks | Model conversion and the checks required before the candidate can be used. Some operations have a stage message without a numerical total. |
| Rescanning and refinement | Frames processed by the existing detector and learned-mask passes. A section pass may include its boundary context. |
| Rendering | Frames written for the requested output interval. |

Training batch updates are throttled to at most one per second; stage changes
and completion can update immediately. Collection updates are throttled
separately. The status reads counters already produced by the work and reuses
existing scan previews. It adds no extra model inference or video decoding just
to animate progress. Preview timestamps identify the source time and image age.

A successful status refresh means the app is reachable. It does not advance
the work counters or reset the last-progress age by itself. Some initialization,
validation, export or long-batch operations can take time without a new count;
use the stage message and logs together. The view retries transient request
failures and catches up when the tab becomes active or the connection returns.
Recent visible log history is bounded so long jobs do not keep growing the page.

## Source files, persistence and boundary review

Candidate and export jobs share the parent source recording. Keep that source
and the persistent job data available for future edits, rescans and exports.
The app prevents deleting a parent while attached jobs still reference it;
remove those child jobs first when deliberately deleting the project. Deleting
or moving the underlying media outside the app can still make future work fail.

Source hashes, FPS and frame counts bind sections to their recording. When a
normalized scan copy came from another original file, its recorded original
checksum is checked as well. A changed source is refused. Back up the original
media and job data together; they include unredacted pixels and private review
information. Interrupted candidates retain the prior approved result and need
an explicit retry after recovery.

Section exports reuse the verified normalized scan copy and existing HDR context;
they do not normalize the whole recording into each new export job. Video codecs
can still require decoding earlier frames to reach a selected interval. This
feature stores reviewed results and renders separate clips; it does not yet cache
finished clips for automatic assembly into a whole-video render.

Rescans read a short context margin around the selected interval to help detect
and track objects near its edges. Only the selected interval belongs to the
candidate and reaches its approved export. Different models can produce
different masks or track identities on either side of a boundary. Inspect the
end of one section and the beginning of its neighbor, particularly moving
plates, occlusions and brief appearances. Context improves the available input;
it does not prove that independently reviewed sections will join seamlessly.

## Verification scope

The automated checks use synthetic recordings, real CPU FFmpeg exports, small
training subprocesses and injected trainer callbacks. They cover exact frame
counts and frame selection, audio timing/redactions, source mismatch, short
decoders, timestamp semantics and preservation of saved review data. These
checks do not measure production NVIDIA training performance or establish
accuracy on a real recording.

Relevant checks for a local checkout:

```sh
pytest -q test_learning_progress.py test_video_sections.py test_section_workflow.py test_section_render.py
pytest -q test_job_polling_browser.py test_sections_browser.py
```

Training keeps its existing CUDA requirement and quality gates. Continue to
review each candidate and its rendered output on your own footage.
