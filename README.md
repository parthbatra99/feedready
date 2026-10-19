<p align="center">
  <img src="assets/art/mascot.svg" width="132" alt="The feedready mascot: a little camera in a beret">
</p>

<h1 align="center">feedready</h1>

<p align="center">
  <b>Hand Claude a phone photo. An experienced Lightroom editor who listens, evolves with you, and gets it ready for the feed.</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Claude_Code-plugin-D97757" alt="Claude Code plugin">
  <img src="https://img.shields.io/badge/macOS-14%2B-000000?logo=apple" alt="macOS 14+">
  <img src="https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white" alt="Python 3.14">
  <img src="https://img.shields.io/badge/Licence-MIT-3DA639" alt="MIT licence">
</p>

<p align="center">
  <picture>
    <source srcset="assets/hero.webp" type="image/webp">
    <img src="assets/hero.gif" width="880" alt="A real session: Claude measures a trek photo, shows three rendered directions, catches its own mistake between v3 and v4, and ships the final with a before/after wipe">
  </picture>
</p>

Claude edits your photo like an experienced Lightroom editor you hired. It reads the photo before touching it, shows you three rendered directions, then edits in versions and checks each one before you see it. You give notes in plain words until it's right.

feedready is early (v0.4.x) and hobby-paced: the edit loop is solid and covered by a self-test, but the recipe format may still change between minor versions.

## It finds the photo you almost took

It measures what the photo has before suggesting anything: hard or soft light and where it sits, colour pairs worth pulling apart, where the eye actually lands. The three directions follow that light instead of the genre, and one runs bold on purpose. Sometimes a direction is a different framing altogether: the square on the face, the vertical out of your landscape, mined from the same pixels. If a crop would cut you out, it asks instead of guessing.

## It edits in parts, like a retoucher

<p align="center"><img src="assets/sees.webp" width="880" alt="The demo photo split into the regions Claude found and edited separately: sky, snow peaks, you, eyes, glove logo, valley and a reflective strip, each with how it was found and what was done to it"></p>

One slider moves the sky, your face and your jacket together, so Claude masks them apart. Apple Vision finds people, faces and eyes on a Mac; small open models do it everywhere else. SegFormer labels the sky, mountains, water, trees and about 150 other scene classes. EdgeTAM cuts out any object you point at, and brightness and colour ranges catch the rest. Masks combine the way you'd stack them in Lightroom: the snow peaks above are the mountain class, minus you, minus the sky. Each part then gets the edit it needs, and a distraction like the reflective strip gets healed out of the photo entirely.

## Talk to it like a photographer

<p align="center"><img src="assets/art/talk.svg" width="880" alt="Six example notes and what Claude does with each: B but darker, warmer, too much, back to v2, show me all versions, ship it"></p>

Every version is saved, so nothing you liked is ever lost. New boards lean toward what you keep choosing: the looks, the amounts, the destinations, all from history that stays on this machine. Already know what you want? Paste an edit list and say `apply`.

## Every round shows its work

<p align="center"><img src="assets/work.webp" width="880" alt="The three edits that changed the demo photo most, each rendered alone as a before and after, with why it was made, its slider values and its measured impact"></p>

Every round renders each edit on its own, zoomed to where it acts, and ranks them by how much they changed the photo, so an edit that changes nothing gets caught. On the Mac you also get a review page with a before/after slider across every version.

## Install

feedready is a plugin, and this repo is its marketplace. Install it once and it's in every chat.

**claude.ai (and the Claude apps signed into the same account).** Go to Customize → Plugins → Add → Add marketplace, enter `dataguyofprocol/feedready`, then Sync. Add **feedready** from the list. In any chat, attach a photo and type `/feedready make this insta ready`.

**Claude Code (Mac).** You need an Apple Silicon Mac on macOS 14+, the Xcode Command Line Tools and `uv` or Python 3.14.

```bash
claude plugin marketplace add dataguyofprocol/feedready
claude plugin install feedready@feedready
```

Then attach a photo in any session and say "make this insta ready". On first use Claude runs setup (it builds the engine) and downloads the models the photo needs, and tells you what it fetched. Finished photos land in `~/Pictures/feedready/`.

## Update

**claude.ai.** Go to Customize → Plugins → Add → Manage marketplaces, open the ⋯ menu on feedready, and choose *Check for updates*. To get updates without asking, turn on *Sync automatically* in the same menu. claude.ai asks you to give the Claude GitHub App access the first time.

**Claude Code.**

```bash
claude plugin marketplace update feedready && claude plugin update feedready@feedready
```

Then run `/reload-plugins`.

<details>
<summary><b>What setup installs on the Mac</b> (about 400 MB, all in <code>~/.cache/feedready</code>)</summary>

| Piece | Size | Used for |
|---|---:|---|
| Python 3.14 venv | ~90 MB download | everything |
| Swift engine | compiled locally from source | Core Image render, Vision masks |
| SegFormer-B0 | 4.4 MB | sky, mountain, water and tree masks |
| EdgeTAM | 41 MB | object masks |
| MI-GAN | 28 MB | object removal |
| YuNet + U²-Net-p | 5 MB | the portable face and subject path (tests, and machines without Vision) |

Models download when a photo first needs them. Setup is safe to rerun. It ends with a `doctor` report; you're done when it says `"tier": "mac"`.

To run setup yourself, or to work on feedready from a clone, see [CONTRIBUTING.md](CONTRIBUTING.md#working-from-a-clone).

</details>

<details>
<summary><b>What you get back</b></summary>

- A quality-100 JPEG at full resolution, next to a `-compare.jpg` before/after. Only the crop changes the size; over 30 MP, Claude asks whether to shrink first.
- Wide-gamut photos (most iPhone shots) stay in Display P3, so saturated colours aren't clipped to sRGB.
- All metadata is stripped, so your post carries no GPS location.

</details>

## On your phone

The same plugin runs in the Claude apps. There, it renders with numpy instead of Core Image, and small open models stand in for Apple Vision: YuNet for faces and eyes, U²-Net-p for the subject, SegFormer + EdgeTAM for people. The first time a chat needs a model, Claude downloads it into that chat's sandbox and says what it fetched. The download uses Anthropic's bandwidth, not your phone's data.

| | Mac | Phone |
|---|:---:|:---:|
| Crops, Lightroom-style sliders, looks | ✅ | ✅ |
| Light and colour reads, recrop suggestions | ✅ | ✅ |
| Shape, brightness and colour masks | ✅ | ✅ |
| Person, face and subject masks | ✅ Vision | ✅ first use downloads ~50 MB |
| Sky and scenery masks | ✅ | ✅ first use downloads 4.4 MB |
| Masks for any object | ✅ | ✅ first use downloads 41 MB |
| Object removal | ✅ | ✅ first use downloads 28 MB |

The portable masks track Vision closely but not exactly: across the test corpus the median overlap is 0.83 for people and 0.88 for subjects. Each chat starts with a clean sandbox, so downloads repeat per chat.

## Your photos stay yours

feedready is a set of tools Claude runs. It has no server, no account and no analytics.

- **Nothing is uploaded.** feedready's only network traffic is downloading models and Python packages. Each model is pinned to an exact file and checked against its SHA-256 before it's used.
- **On a Mac, everything stays on the Mac.** Your photos, every saved version and your taste history live in `~/.cache/feedready/`, and finished photos in `~/Pictures/feedready/`. The engine is compiled on your machine from the Swift source in this repo.
- **On claude.ai, the work stays in that chat's sandbox**, which starts empty each time. Nothing carries over between chats.
- **Exports carry no metadata**, so a post doesn't leak where it was taken.
- **Claude sees the photos you send it.** That's how it edits them, and Anthropic handles them under your account's terms and privacy settings, the same as any image you send Claude. feedready adds no other party.

All of it is open source, so you can check every one of these claims. It's provided as is, without warranty (see [LICENSE](LICENSE)).

## Models: used, not owned

feedready is the tooling: the edit loop, the masks, the renderer and the self-review. The models are one way to find regions in a photo, and they aren't part of feedready. Apple Vision does people and faces on a Mac without any of them, and every shape, brightness and colour mask works with no model at all.

feedready ships no model weights. It downloads each model from its publisher's Hugging Face release, pinned to a revision. Sandboxes that can't reach Hugging Face, such as claude.ai, fall back to this repo's [`models-v1` release](https://github.com/dataguyofprocol/feedready/releases/tag/models-v1), which holds unmodified copies with each model's licence beside it. Each model stays under its own licence, and that licence, not feedready's MIT licence, governs how you use it:

| Model | Licence | Used for |
|---|---|---|
| SegFormer-B0 | [NVIDIA Source Code License](https://github.com/NVlabs/SegFormer/blob/master/LICENSE), non-commercial: research or evaluation only | sky and scenery masks; finding people off the Mac |
| EdgeTAM | Apache-2.0 | object masks; refining people and subjects off the Mac |
| MI-GAN | MIT (its training data is research-only) | object removal |
| YuNet | MIT | faces and eyes off the Mac |
| U²-Net-p | Apache-2.0 | the subject off the Mac |

SegFormer's licence is the strict one: research or evaluation only, which rules out commercial work. Claude mentions this when it downloads SegFormer. If you'd rather not use it, ask for shape and colour masks instead.

## More

<details>
<summary><b>Use it from Codex or another agent</b></summary>

`skills/feedready/` is a standard [Agent Skill](https://agentskills.io). Any agent that reads that format can run it, as long as it can look at images and run shell commands. Clone this repo and build the runtime once with `./feedready/skills/feedready/setup.sh --segformer --models`, then link the skill into the agent's skills folder:

```bash
mkdir -p ~/.agents/skills && ln -s "$PWD/feedready/skills/feedready" ~/.agents/skills/feedready
```

Agents with their own folder, such as `.agent/skills/` in a project, get the same link there. Because it's a link, edits to your clone reach the agent without a version bump.

</details>

<details>
<summary><b>Upload it as a standalone skill instead</b></summary>

If you'd rather not add a marketplace, build the skill bundle from a clone with `./build_zip.sh`, which writes `~/Desktop/feedready.zip`. Upload it under Customize → Skills → Add → Upload skill. To update it, choose Replace from the skill's ⋯ menu and upload a fresh build.

</details>

<details>
<summary><b>Troubleshooting</b></summary>

| Problem | Fix |
|---|---|
| `doctor` says `engine` is missing or out of date | `xcode-select --install` if needed, then ask Claude to rerun setup |
| `needs SegFormer` or `object masks need … EdgeTAM` | Ask Claude to run the `bootstrap` command in the message; it downloads that model |
| A mask spills onto the wrong area | Check the `masks` contact sheet. Subtract `person` or `sky`, tighten the object box, or add `exclude` points. |
| `notes` calls an object mask low-confidence | The box is probably catching two things. Tighten it or add a point inside the object. |
| HEIC fails on the phone | Let Claude run `bootstrap heic`, or send a JPEG. |
| A model won't download | Ask Claude to run `probe`, which shows which hosts the sandbox can reach. Downloads try Hugging Face, then the `models-v1` release on GitHub. If both are blocked, allow one in your claude.ai network settings, or attach the files it lists and let it rerun with `--from`. |
| You want a clean slate for a photo | Delete its folder in `~/.cache/feedready/work/` |

</details>

## Licence

The code is MIT, provided as is, without warranty: see [LICENSE](LICENSE). The models it downloads aren't part of it and keep their own licences (see [Models: used, not owned](#models-used-not-owned)).

Want to drive the engine yourself, read the recipe format, gate a taste change with the blind wow eval, or change the skill? See [CONTRIBUTING.md](CONTRIBUTING.md).
