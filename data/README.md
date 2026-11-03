# Bundled real draft snapshot

`drafts.csv` is the complete canonical schema-v1 artifact regenerated from the
user's Oracle's Elixir raw export, using processor commit
`16493bdcfa4d6b4a362b8cc37e4bbb78c7bbac41`. It is not a synthetic fixture.
The 9,243 games cover January 1 through November 1, 2026 (44 leagues, 20 patches).
`manifest.json` is the production loader's validated public contract;
`provenance.json` records the regeneration evidence without machine-local paths.

The raw input SHA-256 is
`2374ae616a69d6d643b645d4c646b0fe9ba1fc08b16dce152feb567995234590`.
Its recorded local import time is November 1 at 21:02:07 UTC; its original
download time is unknown, so `source_retrieved_at` is null. Regeneration on
November 3 does not imply data newer than November 1. The raw input is not
committed. The new output is byte-for-byte identical to the earlier local
November 1 snapshot, whose original producing revision was not recorded.

Source `year` is preserved as supplied: 3 games say 2025, 9,131 say 2026,
and 109 say 2027, although all observed match dates are in 2026. Do not rewrite
source season context from the date. The processor excluded 614 incomplete or
invalid draft games and dropped 156 incomplete team rows. No role map was
supplied; role feasibility remains explicitly not evaluated.

Data attribution: Oracle's Elixir, https://oracleselixir.com/tools/downloads.
The downloader also documents the source folder at
https://drive.google.com/drive/folders/1gLSw0RLjBbtaNy0dgnGQDAZOHIgCe-HH.
No separate data license accompanied the local import. Third-party data,
trademarks, and other materials retain their owners' rights; the repository's
code license does not grant rights over these materials.

To reproduce, obtain the raw export matching the checksum, build the pinned
processor using Java 21 and Gradle 8.10.2 (`test bootJar`), and run the command
recorded in `provenance.json` with separate input/output directories. The pinned
processor passed 20 tests before generating this artifact. Verify the output
SHA-256 against `manifest.json`, then run:

```sh
python -m rift_atlas.dataset
python -m unittest discover -s tests -v
python scripts/measure_service.py
```

Refresh the CSV, manifest, and provenance together on a feature branch. The
loader uses the working-directory data files; they are bundled by the repository
checkout, not embedded inside the Python wheel. All other local `data/` files
remain ignored.
