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

feedready is early (v0.3.x) and hobby-paced: the edit loop is solid and covered by a self-test, but the recipe format may still change between minor versions.

## It finds the photo you almost took

It measures what the photo has before suggesting anything: hard or soft light and where it sits, colour pairs worth pulling apart, where the eye actually lands. The three directions follow that light instead of the genre, and one runs bold on purpose. Sometimes a direction is a different framing altogether: the square on the face, the vertical out of your landscape, mined from the same pixels. If a crop would cut you out, it asks instead of guessing.

## It edits in parts, like a retoucher

<p align="center"><img src="assets/sees.webp" width="880" alt="The demo photo split into the regions Claude found and edited separately: sky, snow peaks, you, eyes, glove logo, valley and a reflective strip, each with how it was found and what was done to it"></p>

One slider moves the sky, your face and your jacket together, so Claude masks them apart. Apple Vision finds people, faces and eyes. SegFormer labels the sky, mountains, water, trees and about 150 other scene classes. EdgeTAM cuts out any object you point at, and brightness and colour ranges catch the rest. Masks combine the way you'd stack them in Lightroom: the snow peaks above are the mountain class, minus you, minus the sky. Each part then gets the edit it needs, and a distraction like the reflective strip gets healed out of the photo entirely.

## Talk to it like a photographer

<p align="center"><img src="assets/art/talk.svg" width="880" alt="Six example notes and what Claude does with each: B but darker, warmer, too much, back to v2, show me all versions, ship it"></p>

Every version is saved, so nothing you liked is ever lost. New boards lean toward what you keep choosing: the looks, the amounts, the destinations, all from history that stays on this machine. Already know what you want? Paste an edit list and say `apply`.

## Every round shows its work

<p align="center"><img src="assets/work.webp" width="880" alt="The three edits that changed the demo photo most, each rendered alone as a before and after, with why it was made, its slider values and its measured impact"></p>

Every round renders each edit on its own, zoomed to where it acts, and ranks them by how much they changed the photo, so an edit that changes nothing gets caught. On the Mac you also get a review page with a before/after slider across every version.

## Install

You need an Apple Silicon Mac on macOS 14+, the Xcode Command Line Tools and `uv` or Python 3.14.

```bash
claude plugin marketplace add dataguyofprocol/feedready
claude plugin install feedready@feedready
```

Then attach a photo in any Claude Code session and say "make this insta ready". On first use Claude runs setup, which builds the engine and downloads the models the photo needs, and tells you what it fetched. Finished photos land in `~/Pictures/feedready/`.

To update later, run `claude plugin marketplace update feedready && claude plugin update feedready@feedready`.

<details>
<summary><b>What setup installs</b> (about 400 MB, all in <code>~/.cache/feedready</code>)</summary>

| Piece | Size | Used for |
|---|---:|---|
| Python 3.14 venv | ~90 MB download | everything |
| Swift engine | compiled locally | Core Image render, Vision masks |
| SegFormer-B0 (`--segformer`) | 4.4 MB | sky, mountain, water and tree masks |
| EdgeTAM (`--models`) | 41 MB | object masks |
| MI-GAN (`--models`) | 28 MB | object removal |
| YuNet + U²-Net-p (`--models`) | 5 MB | the portable face and subject path (tests, and machines without Vision) |

Setup is safe to rerun. It ends with a `doctor` report; you're done when it says `"tier": "mac"` and `"missing": []`.

To run setup yourself, or to work on feedready from a clone, see [CONTRIBUTING.md](CONTRIBUTING.md#working-from-a-clone).

</details>

<details>
<summary><b>What you get back</b></summary>

- A quality-100 JPEG at full resolution, next to a `-compare.jpg` before/after. Only the crop changes the size; over 30 MP, Claude asks whether to shrink first.
- Wide-gamut photos (most iPhone shots) stay in Display P3, so saturated colours aren't clipped to sRGB.
- All metadata is stripped, so your post carries no GPS location.

</details>

## On your phone

The same skill runs as an uploaded skill in the claude.ai app. It renders with numpy instead of Core Image. Small portable models stand in for Apple Vision: YuNet for faces and eyes, U²-Net-p for the subject, SegFormer + EdgeTAM for people. The first time a chat needs a model, Claude downloads it into that chat's sandbox (Anthropic's bandwidth, not your phone's) and says what it fetched.

| | Mac | Phone |
|---|:---:|:---:|
| Crops, Lightroom-style sliders, looks | ✅ | ✅ |
| Light and colour reads, recrop suggestions | ✅ | ✅ |
| Shape, brightness and colour masks | ✅ | ✅ |
| Person, face and subject masks | ✅ Vision | ✅ first use downloads ~50 MB |
| Sky and scenery masks | ✅ | ✅ first use downloads 4.4 MB |
| Masks for any object | ✅ | ✅ first use downloads 41 MB |
| Object removal | ✅ | ✅ first use downloads 28 MB |

The portable masks track Vision closely but not exactly: across the test corpus the median overlap is 0.83 for people and 0.88 for subjects. Each claude.ai chat starts with a clean sandbox, so downloads repeat per chat. If your sandbox blocks the download, Claude names the files: attach them to the chat and it installs them from there, checking each one's hash.

<details>
<summary><b>Set it up</b></summary>

1. On the Mac, clone this repo (`git clone https://github.com/dataguyofprocol/feedready.git`) and run `./feedready/build_zip.sh`. The bundle lands at `~/Desktop/feedready.zip`.
2. In claude.ai, upload it under Settings → Capabilities → Skills.
3. Attach a photo in any chat and ask for edits.

The zip is a snapshot, so rebuild and re-upload it whenever the skill changes.

</details>

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
<summary><b>Troubleshooting</b></summary>

| Problem | Fix |
|---|---|
| `doctor` says `engine` is missing or out of date | `xcode-select --install` if needed, then ask Claude to rerun setup |
| `needs SegFormer` or `object masks need … EdgeTAM` | Ask Claude to rerun setup with `--segformer --models` |
| A mask spills onto the wrong area | Check the `masks` contact sheet. Subtract `person` or `sky`, tighten the object box, or add `exclude` points. |
| `notes` calls an object mask low-confidence | The box is probably catching two things. Tighten it or add a point inside the object. |
| HEIC fails on the phone | Let Claude run `bootstrap heic`, or send a JPEG. |
| `bootstrap` can't download on the phone | Ask Claude to run `probe`. Allow the blocked domain (huggingface.co, pypi.org) in your claude.ai code-execution network settings, or attach the model files it lists and let it rerun with `--from`. |
| You want a clean slate for a photo | Delete its folder in `~/.cache/feedready/work/` |

</details>

<details>
<summary><b>Model licences</b></summary>

| Model | Licence | Used for |
|---|---|---|
| SegFormer-B0 | [NVIDIA Source Code License](https://github.com/NVlabs/SegFormer/blob/master/LICENSE), non-commercial: research or evaluation only | sky and scenery masks; finding people off the Mac |
| EdgeTAM | Apache-2.0 | object masks; refining people and subjects off the Mac |
| MI-GAN | MIT (its training data is research-only) | object removal |
| YuNet | MIT | faces and eyes off the Mac |
| U²-Net-p | Apache-2.0 | the subject off the Mac |

SegFormer's licence is the strict one. It allows use only "for research or evaluation purposes", which rules out commercial work and may not cover everyday posting either. Read it before relying on sky, scenery or (off the Mac) person masks. Everything else works without it.

`bootstrap` downloads each model from Hugging Face, or from this repo's [`models-v1` release](https://github.com/dataguyofprocol/feedready/releases/tag/models-v1) when Hugging Face is blocked. The release holds unmodified copies with each model's licence beside it.

</details>

## Licence

The code is MIT — see [LICENSE](LICENSE). The models `setup.sh` and `bootstrap` download keep their own licences, listed above; SegFormer's is limited to research or evaluation.

Want to drive the engine yourself, read the recipe format, gate a taste change with the blind wow eval, or change the skill? See [CONTRIBUTING.md](CONTRIBUTING.md).
