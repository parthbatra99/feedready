---
tags: ["behaviour", "masks"]
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep]
---

Use the feedready skill: load it with the Skill tool and read its reference files before you answer. You are in the middle of a feedready session on claude.ai. You can't run commands in this exercise; the command output you would have seen is pasted below, exactly as the CLI printed it.

Three convocation photos of the user's brother. v3 used this recipe on the duo shot:

```json
{"steps": [
 {"name": "recover highlights", "adjust": {"highlights": -29}},
 {"name": "calm the background", "mask": {"type": "person", "invert": true, "grow": -0.004}, "adjust": {"exposure": -0.35, "highlights": -20}},
 {"name": "lift the faces", "mask": {"type": "face", "index": "all"}, "adjust": {"exposure": 0.45, "shadows": 15}},
 {"name": "clean grade", "look": "natural"},
 {"name": "golden warmth", "look": "warm-golden", "amount": 60}
], "vignette": -10}
```

`inspect` found two faces, the brothers (index 0 and 1), and the people models are installed.

The user said: "give skin fair. you made it golden too"

Write the step(s) you add for v4 as JSON in a ```json block, then one line on what you read the note as.
