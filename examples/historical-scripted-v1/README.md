# Historical scripted capture cohort

These original 40 bundles and index files are retained byte-for-byte from the first offline demonstration. The adapter source is retained at commit `371106b`.

Independent review found that request events held the input message array by reference. Later replies/tool results were appended before serialization, so the recorded request frames contain future messages. These records must not be used as accurate model-request provenance or as live-model evidence. No paid calls occurred; subject and judge replies were authored scripts.

The corrected adapter snapshots each emitted payload. The current cohort in `examples/scripted` was captured afresh with new run IDs, timestamps, hashes and parent links after that correction. Historical records were not reconstructed or relabelled as corrected captures.
