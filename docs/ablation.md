# Simplification experiments — 0.2.0

Date: 2026-09-11. Baseline: [`f0eca34`](https://github.com/cunninghamcard-bit/omarchy-niri/commit/f0eca34c34b1b6ddfed845ca8db56183dec4f87f).
The objective is less maintained code and fewer indirections with the existing
behavior and installation protections retained.

## Controlled comparisons

Every variant is assembled in a temporary directory. The baseline and independent
variants use the same 26 contract tests (the original 25 plus the successful
checkout-upgrade test) and 11 JavaScript event-model assertions. The three new
patch tests also run in variants that support patches. No variant is installed
on the desktop. Negative controls deliberately remove one protection at a time.

| Variant | Maintained lines | Python tests | Result | Decision |
| --- | ---: | ---: | --- | --- |
| Baseline | 11,466 | 26 | Pass | Reference |
| Only replace 22 upstream copies with standard patches | 4,498 | 29 | Pass; all 87 generated files byte-identical | Keep |
| Only share installer link/conflict/rollback paths | 11,460 | 26 | Pass; all 87 generated files byte-identical | Keep |
| Extract more runtime helper functions | 11,506 | 26 | Pass, but adds six functions and another layer of calls | Reject |
| Only remove unused runtime function/import | 11,461 | 26 | Pass | Keep |
| Combined selected changes | **4,484** | **29** | **Pass** | **Ship** |

The line metric covers `manage.py`, `install.sh`, `payload/`, and `patches/`,
including blank lines and diff context; it excludes tests, docs and manifest
metadata. The reduction is **6,982 lines (60.9%)**, mostly verbatim upstream
copies removed from this repository. Installed desktop files are still present.
Python control code changes from 851 to 846 lines overall.

The patch-only variant reconstructs the exact bytes of all 87 baseline managed
files from the pinned Omarchy source. In the combined variant, 86 files remain
byte-identical; the only changed runtime file is `default/niri/desktop.py`, where
an unused function and import were removed. The eight directional bindings,
Quickshell code, scrolling and empty-space configuration are unchanged.

## Removal controls

All four controls failed on the intended behavior checks. These protections
remain in the selected implementation.

| Removed logic | Observed failures | Why it stays |
| --- | --- | --- |
| Refresh journal recovery | Four tests fail: publication rollback, state-write rollback, interrupted refresh, committed refresh recovery | One shared path handles both exceptions and interrupted publication |
| Conflict preflight | Restore test fails because an earlier file is restored before a later conflict is detected | Detect conflicts before partially restoring files |
| Generated-output hash check | Damaged replacement and corrupt-patch tests fail | A syntactically valid patch can still generate unintended contents |
| IPC error propagation | Real local-socket test fails to receive the compositor error | Desktop failures must remain visible to callers |

Short command wrappers remain plain scripts. A central wrapper registry was
reviewed but not implemented or counted as an experimental variant: it would
add dispatch machinery to commands that are already one line long. Files with
multiple official/ARM baselines remain complete replacements so a single-base
patch cannot silently erase variant-specific differences.

## Reproduce

Use a full clone of this repository and a clean checkout of Omarchy commit
`346e69e1cec6c4e8924531874af6ba010a1bc99e`:

```sh
python3 tests/ablation.py --base /path/to/omarchy
python3 tests/check_payload.py --base /path/to/omarchy
```

Results and per-variant logs are written to `test-artifacts/ablation/`.
The [recorded result data](evidence/ablation-results.json) includes the exact
failed-test names. CI repeats the matrix and uploads the full logs. The rejected
helper-extraction patch is kept only as an experiment fixture.

Two independent reviewers checked installer recovery/update compatibility and
the compositor/configuration boundary. These experiments establish equivalence
within the tested contracts and exact generated-file comparison. They do not
prove a globally minimal design, and no new graphical or physical multi-monitor
acceptance is claimed; see the historical [runtime evidence](acceptance.md).
