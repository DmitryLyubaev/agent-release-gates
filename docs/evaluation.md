# Evaluation method

Sixteen new synthetic source families are divided into four calibration, eight held-out and four release families. Each calibration/held-out family has a natural explanation and an identified mutated counterpart, yielding eight calibration and sixteen held-out review items. Paired variants are not independent observations. The separate release experiment compares four cases per version.

The human labels support (yes/no/unclear) and usefulness (yes/no) without seeing judge verdicts or mutation origin. Only calibration data may guide tuning; holdout begins after the combined dataset/rubric/judge identity is frozen. Two repetitions each need at least 14/16 combined-label agreement, no dangerous false accepts, at least four human-acceptable items and four human-confirmed dangerous negatives. All confusion counts, abstentions and denominators are retained.

Exact monetary/source/reference/action checks cannot be overridden by a favourable judge. Missing evidence, an unqualified judge, unresolved cost or incompatible identities prevents acceptance. Decisions snapshot the actual evaluations, qualification, label revision and policy through immutable database records. Original agent capture time and later judge/replay time are separate measurements.

The current implementation has scripted model and judge adapters only. Synthetic test labels are marked scripted; they cannot establish a human/live qualification. No historical transcripts are reconstructed and no independent-human, live-model, production or accuracy claim follows from offline success.
