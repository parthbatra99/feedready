---
tags: ["behaviour", "masks"]
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep]
---

Use the feedready skill: load it with the Skill tool and read its reference files before you answer. You are in the middle of a feedready session on claude.ai. You can't run commands in this exercise; the command output you would have seen is pasted below, exactly as the CLI printed it.

Two brothers at a convocation, holding their degrees in front of a bright yellow wall. `inspect PHOTO --fetch` printed (summary shown; the full fields follow it):

```json
{
 "summary": {
  "tier": "portable",
  "fetched": [
   "segment (4.4 MB)",
   "people (45.7 MB)"
  ],
  "faces": [
   {
    "index": 0,
    "box": [
     0.31,
     0.17,
     0.41,
     0.27
    ],
    "main": true
   },
   {
    "index": 1,
    "box": [
     0.55,
     0.12,
     0.64,
     0.21
    ],
    "main": true
   },
   {
    "index": 2,
    "box": [
     0.02,
     0.4,
     0.04,
     0.43
    ],
    "main": false
   },
   {
    "index": 3,
    "box": [
     0.88,
     0.38,
     0.9,
     0.41
    ],
    "main": false
   }
  ],
  "masks": [
   "radial",
   "linear",
   "brush",
   "polygon",
   "luminance",
   "color",
   "person",
   "subject",
   "background",
   "face",
   "skin",
   "segment",
   "sky",
   "object"
  ],
  "missing": [],
  "genre": "group",
  "hero": "faces",
  "findings": [
   "1.1% of pixels are clipped to white",
   "the background is 1.3 stops brighter than the face, so the eye goes to the background first"
  ],
  "opportunities": [
   "balanced light (1.0 stops of range); highlights run cooler than the shade"
  ],
  "recrops": []
 }
}
```

The user replied: "A, the clean one. Just make both our faces brighter than that wall."

Write the recipe for v1 as one JSON object in a ```json block: a clean `natural` grade, the background calmed, and both brothers' faces lifted. Then one line on what it does.
