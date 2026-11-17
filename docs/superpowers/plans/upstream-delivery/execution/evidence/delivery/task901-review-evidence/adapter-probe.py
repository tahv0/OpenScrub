import json, sample
print("REVIEW_PROBE " + json.dumps({"origin": sample.__file__, "value": sample.VALUE}))
