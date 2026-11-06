---
tags: ["behaviour", "masks"]
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep]
---

Use the feedready skill: load it with the Skill tool and read its reference files before you answer. You are in the middle of a feedready session on claude.ai. You can't run commands in this exercise; the command output you would have seen is pasted below, exactly as the CLI printed it.

A couple at a restaurant dinner table; behind them are other diners and a waiter. `inspect` printed:

```json
{
 "summary": {
  "tier": "portable",
  "faces": [
   {
    "index": 0,
    "box": [
     0.25,
     0.34,
     0.41,
     0.45
    ],
    "main": true
   },
   {
    "index": 1,
    "box": [
     0.57,
     0.37,
     0.74,
     0.48
    ],
    "main": true
   },
   {
    "index": 2,
    "box": [
     0.001,
     0.46,
     0.037,
     0.49
    ],
    "main": false
   },
   {
    "index": 3,
    "box": [
     0.54,
     0.46,
     0.56,
     0.48
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
   "the person is 1.9 stops darker than the background (skip if the silhouette is the look)"
  ]
 }
}
```

`masks` on a test recipe showed the `person` mask covers the couple and also the diners and waiter behind them.

The user said: "B, bright and airy. Lift just the two of us, not the people behind."

Write the step (one JSON object in a ```json block) that lifts only the couple: exposure +0.25, shadows +20. Then one line on why that mask.
