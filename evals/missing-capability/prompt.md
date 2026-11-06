---
tags: ["behaviour", "capabilities"]
max_turns: 25
timeout_seconds: 600
allowed_tools: [Skill, Read, Glob, Grep]
---

Use the feedready skill: load it with the Skill tool and read its reference files before you answer. You are in the middle of a feedready session on claude.ai. You can't run commands in this exercise; the command output you would have seen is pasted below, exactly as the CLI printed it.

A photo of a golden retriever on a busy patterned rug. `inspect PHOTO --fetch` printed:

```json
{
 "summary": {
  "tier": "basic",
  "fetched": [
   "segment (4.4 MB)",
   "people (45.7 MB) FAILED: could not download https://huggingface.co/...: curl: (56) CONNECT tunnel failed, response 403"
  ],
  "faces": [],
  "masks": [
   "radial",
   "linear",
   "brush",
   "polygon",
   "luminance",
   "color",
   "segment",
   "sky"
  ],
  "missing": [
   "people: run `feedready.py bootstrap people` (50.1 MB download)",
   "object: run `feedready.py bootstrap object` (40.9 MB download)"
  ],
  "genre": "still life / interior",
  "hero": "subject"
 }
}
```

The user said: "make the dog pop, the rug is too busy"

Say what you do next and why, as the message you'd send plus the commands you'd run.
