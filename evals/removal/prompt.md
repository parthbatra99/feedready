---
tags: ["behaviour", "masks"]
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep]
---

Use the feedready skill: load it with the Skill tool and read its reference files before you answer. You are in the middle of a feedready session on claude.ai. You can't run commands in this exercise; the command output you would have seen is pasted below, exactly as the CLI printed it.

A red Ferrari F50 in a museum hall. `inspect` printed:

```json
{
 "summary": {
  "tier": "portable",
  "fetched": [
   "segment (4.4 MB)",
   "people (45.7 MB)"
  ],
  "faces": [],
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
  "genre": "still life / interior",
  "hero": "subject"
 }
}
```

`bootstrap heal` already ran (MI-GAN is installed). Reading the grid: two silver stanchion stands sit left of the rear wheel, one around x 0.08–0.15, y 0.52–0.71 and one around x 0.02–0.10, y 0.56–0.82; a "please do not touch" sign stands at x 0.12–0.24, y 0.69–0.81.

The user said: "remove the stands and the sign"

Write the removal step(s) as JSON in a ```json block.
