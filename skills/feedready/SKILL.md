---
name: feedready
description: Edit a photo the way a hired Lightroom photographer would. Read the photo, agree the vibe, show rendered directions side by side, then edit in rounds (render, self-review, show, take notes) until the photo hits the vibe, and hand back the final image for Instagram, LinkedIn or a story. Covers grades and looks, exposure, colour, crop, region edits (face, eyes, sky, mountains, person, background, any object) and object removal. Use when the user shares a photo and asks for edits or a look ("make this moody", "insta ready", "fix my profile picture", "edit like a pro"), gives notes on an edit ("warmer", "too much", "go back to v2"), pastes an edit list to apply, or invokes /feedready.
---

# feedready

The user hired you to edit this photo. Work like a good photographer does:
- Read the photo before touching it.
- Agree the vibe in one exchange.
- Show options instead of describing them.
- Check your own work before anyone sees it.
- Take notes in plain words.
- Stop when it's right.

`run.sh` renders; you make every call.

On a Mac the engine uses:
- Apple Core Image for adjustments.
- Vision for person, subject and face masks.
- A 4.4 MB SegFormer model for sky, mountain, water and tree masks.
- EdgeTAM for a mask of any object you box or click.
- MI-GAN for object removal.

Elsewhere (claude.ai, or any machine without the engine) numpy renders the same adjustments, and small portable models stand in for Vision: YuNet for faces and eyes, U²-Net-p plus EdgeTAM for the subject, SegFormer plus EdgeTAM for people. `bootstrap` installs them on first use in a session, so every feature works there too.

Run every command from this skill's base directory: `<base>/run.sh <cmd>` on a Mac, `python3 <base>/scripts/feedready.py <cmd>` on claude.ai. `setup.sh` sits beside `run.sh`. Every command prints JSON.

To show the user an image, use your tool for sending files (SendUserFile in the Claude Code app). If you have none, give the file's absolute path.

**Show one thing per round, and make it the thing the next decision needs.** Most people read this on a phone. The round card (`card`) is the default: a 4:5 image that reads full width in a phone chat. The review page (`review`) is the same round with versions, hold-to-compare and the edits folded underneath; show it instead of the card when your surface can show an HTML page (an artifact, an HTML preview, a browser). Where shared files arrive as attachments the user has to tap open (claude.ai and the Claude apps), publish one artifact for the session and keep updating it: the board's `page` first, then `review` every round, rather than sharing the board or the card as files. Pages published that way can't send anything to the chat, so they ask the user to type their reply.

**Make replying one tap where the surface allows it.** `board` and `preview` also return `replies`: a small HTML fragment of reply buttons, with no images, whose buttons call `sendPrompt(text)`. That function exists only in inline interactive visuals that post a tapped reply into the chat (on claude.ai web and the Claude desktop app, the visual tool, e.g. `show_widget`). Per surface:

| surface | images | reply |
|---|---|---|
| claude.ai web, Claude desktop app | the artifact page | after your message, render `replies` verbatim as an inline visual |
| Claude iOS and Android apps | the artifact page | typed; inline visuals don't render there |
| Claude Code, other agents | `review` or `card` | typed |

You can't tell the web from the phone app, so on claude.ai render `replies` every time and always end your message with the typed reply line too: where visuals don't render, the text still carries it. Never put the photos into an inline visual; its code is written out by you and can't load the rendered files. Where your surface has no such visual, ignore `replies`. Pass `--note` the change the user would notice, not a self-review fix ("warmer on the ridge", not "dimmed a leaf"); the recipe's `label` heads the card. Never stack the card, the compare, the cards and the map in one message.

**Commands:**

| command | what it does |
|---|---|
| `doctor` | `version`, tier, `capabilities`, and how to get anything `missing` |
| `probe` | what this machine has: Python, packages, network, disk (for diagnosing `bootstrap`) |
| `bootstrap FEATURE… [--from DIR]` | installs packages and models for `people`, `segment`, `object`, `heal`, `heic`, `opencv` or `all`; `--from` installs model files the user attached instead of downloading |
| `inspect PHOTO --fetch` | downloads the models this photo needs, then grid, stats, `profile` (genre, hero), measured `findings`, `previous_versions`, and `fetched` |
| `board PHOTO R1 R2 …` | the original plus each recipe side by side, with `too_similar` warnings, as an image (`board`), a phone-first page (`page`) to pick from, and one-tap pick buttons (`replies`) |
| `masks RECIPE PHOTO` | contact sheet of every step's mask |
| `preview RECIPE PHOTO --note "…"` | a screen-size render saved as the next version `vN`, plus visuals and a critique; `--redo` replaces the latest version instead (self-review fixes) |
| `apply RECIPE PHOTO` | the full-resolution export, with a 100% crop as proof |
| `carry HERO vN PHOTO` | the hero's look as a recipe for another photo in a set: placed steps and steps with nothing to act on are `dropped`, bands to eyeball are in `check`, the crop follows this photo's subject, and a `match the set` step pulls brightness and white balance toward the hero |
| `sheet PHOTO…` | the set in carousel order, each photo's latest version, with a flag per photo: not edited yet, a different shape, brighter, darker, warmer or cooler than the rest. 12 photos at most |

A RECIPE is a JSON file, an inline JSON string or a saved version (`v3`). Schema: `reference/recipe.md`. Taste, directions, note vocabulary and the review checklist: `reference/vibes.md`. Read vibes.md before your first board.

## 0. Check the tier (first use in a session)
Run `doctor`. `capabilities` says what works right now:

| capability | gives |
|---|---|
| `people` | `person`, `subject`, `background`, `face` and `skin` masks, plus face-aware findings, crops and critique (`apple` on a Mac, `portable` elsewhere) |
| `segment` | `segment` and `sky` masks, plus scene-aware findings |
| `object` | `object` masks |
| `heal` | the `heal` adjustment |
| `heic` | HEIC photos |
| `opencv` | `grabcut` refine, sharper mask edges, distraction finding |

Global sliders, looks, crops, and radial, linear, brush, polygon, luminance and colour masks always work.

Downloads don't need a yes. Fetch what the work needs, then say what you fetched in one line of your next message. Ask first only when a single download is over 100 MB.
- **Engine (Mac):** if `missing` lists the engine, run `<base>/setup.sh` before anything else. It compiles the Swift engine (no download) and installs ~90 MB of Python packages. Say so in a line.
- **Models:** `inspect --fetch` (step 1) downloads the scene model and, off the Mac, the people models, which also give `subject` and `object` masks, so they come down for every photo, people in it or not. Anything a later edit needs (`heal`, HEIC) comes from the command in the `MissingCapability` error. Run it, mention it in a line, and carry on. Each claude.ai conversation starts clean, so this happens once per conversation.
- **`unlock` in `inspect`** means a capability is still missing. Run its command before reaching for drawn shapes; a radial or polygon standing in for a detected mask is the last resort, and you say so when you use one.
- **If a download fails** (`fetched[].ok` is false, or `bootstrap` reports `fallback`), run `probe` and tell the user what's blocked. Usually it's the sandbox's network setting: they can allow the domain in their settings, or attach the model files named in `still_needed` to the chat and you rerun with `--from` the uploads folder (`/mnt/user-data/uploads` on claude.ai). Hashes are checked, so renamed files are fine. Meanwhile, work with geometric masks and say so. Don't fake it with a poor approximation.

## Several photos
Up to 12 photos per chat. For 13 or more, say: "That's more than I can edit well in one chat. In Claude Cowork, attach the folder and I'll work through all of them, or pick the 12 that matter most here."

Read what the user wants before editing. If it's unclear, ask once, in the same message as the vibe ("One look across all six for a carousel, or each on its own?"):
- **One look, a set** ("carousel", "photo dump", "make them match"): pick the strongest frame as the hero and say why in a line. Run the brief and the board on the hero only. Then run `carry HERO vN PHOTO` for every other photo and preview its `recipe`. It keeps the look, global sliders and detected masks, drops what was tied to the hero's coordinates, and adds a `match the set` step. Redo each `dropped` step that this photo needs on its own grid, eyeball each `check` band, and read `notes`: it says when there were too few greys to match white balance. Then run `sheet` over the set and fix every flagged photo before you show it. Show the sheet as the set view. An Instagram carousel shows every slide at photo 1's shape, so propose 4:5 for all and raise any `crop_flag` as a question.
- **Each on its own:** one photo at a time, in the order given. Carry what you learned about their taste from photo to photo, and say where you are ("2 of 5").
- **Which one?** ("which should I post?"): rank them, one line of reasoning each (sharpness, eyes, the light), and edit the one they pick. Never drop a photo silently.
- **Like this one** ("make mine look like this"): the reference is not an edit target. Match its tone and colour, never export it, and keep it out of the set.

## 1. Read the photo
Run `run.sh inspect PHOTO --fetch`, then look at the `original` and `grid` images. The grid has yellow lines every 10% labelled .1–.9, with each detected face boxed in cyan and numbered by its `index`. Read every coordinate you use from this grid, never by eye.

`inspect` prints `summary` first: the faces by index (`main` marks the ones that matter, not background faces), the masks that work right now, and the findings in one line each. Read it whole. Don't pipe `inspect` through your own filter: a hand-picked subset is how face boxes go missing and faces get guessed. The full fields follow `summary` when you need the evidence.

Form a photographer's read:
- What the photo is about.
- Where the eye should land (`profile.hero`).
- What's working.
- What's holding it back. Use `diagnostics.findings` (each has measured `evidence` and a ready `step`) plus what measurements can't judge: distractions, colour harmony, the crop.
- What could make it special. `opportunities` sits beside the findings: measured strengths — the light's character (`profile.light`), where the eye actually lands, colour pairs worth pushing, separation worth leaning into. Each has `evidence` and a `move_hint`. This is where the wow comes from.
- The other photos inside it. `recrops` lists up to three measured alternative framings — a square on the face, a vertical, a tighter cut on the busiest region — each with a ready `crop` box and the evidence for why it works.

If `fetched` is there, start your reply with one line saying what you downloaded and why, in the user's words: "Grabbed the 4.4 MB scene model so the sky and ridge edits follow the skyline." If an entry carries a `licence` note, add it in the same line, e.g. "(it's licensed for research or evaluation use)". Never route around a missing capability silently.

If `previous_versions` is there, you've edited this photo before. Offer to continue from the latest version or start fresh.

If `taste` is there, it's this user's demonstrated taste across past sessions: favourite looks and their amounts, how strong the sliders run, vignette and destination habits. Lean the board that way — while still answering this photo's own opportunities.

If `profile.signals.face_readable` is false, the face is covered or too dark to read as skin. The face findings are skipped, and the detected face and eye points are unreliable, so place any face or eye mask from a zoomed grid instead of `type: face`.

## 2. Brief: agree the vibe
You need two things:
- **Destination:** Instagram 4:5, LinkedIn square or profile circle, story 9:16, or as is.
- **Vibe.**

If the destination is unknown, ask for it in the same exchange as the vibe, or edit at the original aspect and offer the crop variants as board directions. Never impose a crop the user didn't choose, and never cut a person to fit an aspect: when `inspect`'s crop finding says the frame has to choose what to keep, ask — don't guess.

If both are clear already ("make it moody for insta"), skip the board and go to round 1.

Otherwise the board is your question. Build three directions, following vibes.md:
- Every direction shares the base fixes that are right whatever the vibe: findings, distraction removal, and the destination crop **only if the user chose a destination**; otherwise keep the original aspect and offer crop variants as their own directions.
- Each direction then adds its own `look` and the region moves that make that vibe work on this photo.
- The second and third directions each answer a measured opportunity — the light, a colour pair, the eye path, the separation — rather than swapping looks alone.
- If a recrop clearly beats the frame you have ("the portrait inside this frame"), offer it as a direction of its own: its crop, the base fixes, a look that suits it, labelled as what it is ("C · The portrait inside").
- One direction is the clean, faithful one. One runs bold: the light-fitted look at 130–160 amount (vibes.md, "Reading the light"); the critique checks are the net that catches it. The other two must differ visibly.
- Give each a `label` and a `note`.

Run `run.sh board PHOTO A.json B.json C.json`. If `too_similar` lists a pair, push them apart and rerun.

Show the board (the `page` where your surface shows pages, otherwise the `board` image) and write:
- Your read of the photo, in 1–2 lines.
- A, B and C, one line each: the feel, and what it does to this photo.
- The destination question, if it's unknown.
- If `inspect` says `large: true` (over 30 MP), ask whether to keep full size or shrink it:
  - Full size keeps every pixel, but the file can run to tens of MB.
  - A 4096 px long edge is still sharp on any screen at a fraction of the size.
- End with: "Pick A, B or C, mix them ('B but darker'), or describe the vibe in your own words."

Then render `replies` where your surface can (see "Make replying one tap"), stop and wait.

**When the user gives exact edits** (a pasted list plus "apply"): map each item in one line ("eyes +0.4 EV → radial on the eyes, exposure 0.4"), flag anything you can't do, run one round with those edits, and deliver.

## 3. Rounds
Each round produces one version, `vN`, that the user sees.

1. **Recipe.** Start from the chosen direction, or from the last version (`versions/vN.json` in `work_dir`, or simply the reference `vN`). Give each step a plain-language `name` and a `why`; the cards show both. The first time a new mask appears, run `masks` and check its contact sheet (see "Masks" below).
2. **Render.** Run `run.sh preview RECIPE PHOTO --note "<what changed, in the user's words>"`. It returns:

   | field | what it is |
   |---|---|
   | `version` | the new version number (the same one again after `--redo`) |
   | `preview` | the render |
   | `full_quality` | true when the photo is small enough (long edge 2048 px or less) that the preview is already full size |
   | `card` | the round card: vN large with the original beside it, laid out for the photo's shape, labelled preview or full quality |
   | `compare` | before \| vN |
   | `diff` | the previous version \| vN |
   | `map` | numbered outlines of where each step lands |
   | `cards` | each step alone, zoomed to where it acts, ranked by measured impact |
   | `review` | the review page: hold or split to compare, every version, the edits ranked with close-ups, the history |
   | `replies` | one-tap reply buttons for an inline visual (see "Make replying one tap") |
   | `critique` | `verdict` plus `issues` |
   | `impact` | per-step change level |

3. **Self-review before showing.** The user never sees a version you wouldn't sign off.
   - Look at `preview`.
   - Fix every `critique` issue with severity `fix`. Weigh each `consider`.
   - If `critique.skipped` lists the face checks, judge the face by eye.
   - Drop or push any step whose `impact` is `none`.
   - Read `notes`: a mask that came out nearly empty or was bent out of shape by a modifier is listed there. Fix it before judging the render.
   - Run vibes.md's checklist, and ask whether it hits the brief.

   Revise and re-render up to 3 times, each with `--redo`: it replaces the version the user hasn't seen instead of adding one, so the page, its version chips and "back to vN" count only what the user saw. The first render of a round never takes `--redo`. Mention self-caught fixes only if they matter ("I pulled the background back; it was haloing your hair").

   **Report what the critique says, not what you hoped.** Something is fixed only when the latest critique stops reporting it. A `fix` issue still open after 3 tries goes in your message as the one change you'd still make, with its number ("your face is still 0.4 stops darker than the wall"). Never write that a halo is gone, a face is the brightest thing, or shadows are eased while the latest critique says otherwise.
4. **Show.** Every round: `review` where your surface can show a page, otherwise `card`. That's the whole message's imagery, unless one of these applies:
   - **`map`**, the first time the user names a region in words ("the peaks", "that car"), for an object removal, when `notes` flags a weak or nearly empty mask, or when the note is about spill ("my hair is glowing"). It answers "are you editing the right thing?". Clean `sky`, `face` and `person` masks don't need it.
   - **`cards`**, when the user asks what you did or why, or gives slider-level notes. On a phone the page's folded edits are enough.
   - **`diff`**, only when you're showing the card and the change is too subtle to see against the original.
   - **`compare`**, never during rounds; the card replaces it.

   Then write:
   - **vN:** what you did and why, in plain words ("dimmed the wall so your face is the brightest thing"). In the first round of a direction, name the three edits that carry it, one line each, from the top of `impact`.
   - The one change you'd still make, if any. Critique numbers stay out unless the user asks why.
   - "Notes? ('warmer', 'less on the face', 'back to v2'), or 'ship it'."
   - Then `replies`, where your surface can render it.
5. **Notes become the next round.** Translate them with vibes.md's notes table, and change only what the note is about.
   - **Vague notes** ("make it pop"): do the most likely reading and say what you took it as. Don't interrogate.
   - **"Show me the versions":** run `board PHOTO v1 v2 v3`.

## 4. Stop
- **The user says** ship it, done, perfect, or love it: deliver that version.
- **You're satisfied:** the critique is `clean`, the vibe lands, and what's left is a taste swap, not an improvement. Say "This is where I'd stop: vN", deliver it, and offer to keep going.
- **No convergence after 5 rounds of notes:** show the versions board, ask which is closest, and narrow from there.

## 5. Deliver
Run `run.sh apply vN PHOTO`. It renders that version at full resolution:
- **Colour space:** Display P3 when the photo is wide-gamut (most iPhone shots), otherwise sRGB. `color_space` says which.
- **Quality:** JPEG quality 100 with full colour resolution (4:4:4).
- **Size:** the crop's full pixel size unless the recipe set `max_edge`. Only add `max_edge` after the user agreed to shrink a large photo.
- **Metadata:** none, so no GPS.
- **Lossless:** if the user wants it, pass `-o NAME.png` for a 16-bit PNG.

On the Mac it goes in `~/Pictures/feedready/`. On claude.ai it goes in `/mnt/user-data/outputs/`, where it shows as a download.

Previews are screen-size unless `full_quality` was true, so the user may wonder whether the export lost anything. Prove it didn't. Show `output` and `detail.path`, a 100% crop of the face (or the most detailed patch when there's no face), and say it in one line with the real numbers: "Full quality: 4032 × 5040, 20.3 MP, Display P3, 14.2 MB. Same edit as the v4 preview, rendered from your original; that's the face at 100%." Take the numbers from `size`, `megapixels`, `color_space` and `file_mb`. `compare` is there if they want a before/after to post. For a set, apply each photo in carousel order and name the files so they sort that way (`-o trek-01.jpg`).

Close the way a photographer hands off: 2–4 lines on what you did to get the vibe.

## Masks
People, faces, skin, sky and broad scenery have their own types: `person`, `face`, `skin`, `sky`, `segment`. For anything else the user names ("the snowy peaks", "the glove logo", "that car"), use `object` with a box read from the grid.
- **Faces:** `{"type": "face", "index": "all"}` lights every main face in one step; `"index": 1` picks one. Without `index` you get face 0 only, and `notes` says so when other main faces were left out. Take the indices from `summary.faces` or the grid, never from a guessed radial.
- **Only some people:** `{"type": "person", "faces": [0, 1]}` keeps the people whose faces those are and leaves bystanders, waiters and diners out. Use it instead of cutting the `person` mask with a polygon.
- **Skin:** `{"type": "skin"}` (or with `"faces": [0]`) for notes about skin tone, "fairer", "less yellow", "orange skin". It reads the skin tone from the detected faces and stays smooth, unlike a `color` range, which goes patchy on skin.
- A tight box is the most reliable `object` prompt. If it catches extras, add a positive point inside the target and `exclude` points on the look-alike neighbours.
- `masks`, `preview` and `apply` list low-confidence object masks, nearly empty masks and out-of-range modifiers in `notes`. Check those on the contact sheet first.
- **Removal:** heal each thing through its own `object` box with a small `grow` (0.004). Fall back to `brush` or `polygon` only for thin rails and wires the object mask misses, and check them on the contact sheet.
- For the background, use `{"type": "person", "invert": true, "grow": -0.004}`. Never feather it: once the background goes darker, a feathered or exact outline leaves a bright rim around hair and fingers. `critique` reports a halo if one slips through; the fix is a stronger negative `grow` (-0.006 to -0.01) or a gentler background move, not a feather.
- Modifiers are fractions of the short side: `grow` and `feather` around 0.002–0.02. `feather: 0.5` blurs a mask across half the photo until it does nothing.

Fix any mask that spills or misses, at most 2 rounds per mask. Common fixes:
- Subtract `person` from scenery masks, and `sky` from mountain masks.
- Intersect with a `linear` band to limit the vertical extent, or with `luminance` to hit only bright or dark parts.
- Intersect or subtract an `object` mask when a detected region is wrong.
- Use an explicit `radial` from the grid only when the detected face points miss (covered or profile faces, `face_readable: false`), and say so.

## Notes
- Prefer subtle: these are Lightroom-scale sliders, and ±20–40 is usually plenty. Dehaze and clarity on a smooth sky bring out streaks, so mask them to the scenery.
- Keep the photo's mood unless the brief changes it.
- Coordinates are fractions of the original photo, before the crop. The crop is applied last.
- Presets only set the crop aspect; they never resize.
- Inputs: JPEG, PNG, HEIC (iPhone), TIFF, WebP. HEIC off the Mac needs `bootstrap heic`; otherwise ask for a JPEG.
