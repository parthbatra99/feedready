---
type: llm
weight: 2
---

Look at the recipe JSON. PASS if the face lift uses detected face masks that cover both brothers (faces 0 and 1): either `"index": "all"` or separate steps for index 0 and index 1. FAIL if it lifts only one face (a face mask with no index, or only index 0), if it lifts the small background faces 2 or 3 on purpose, or if it places faces with guessed radial ellipses.
