# The offline CRNN engine

`OCR_ENGINE=crnn` runs the from-scratch model from
[`Sanaharu-Santosh/NoteBook`](https://github.com/Sanaharu-Santosh/NoteBook) —
a CNN + bidirectional LSTM trained with CTC loss — with no network, no API key
and no per-call cost.

```bash
pip install -r requirements-crnn.txt   # TensorFlow, ~600MB
# then OCR_ENGINE=crnn in backend/.env
python scripts/eval_crnn.py            # measure it
```

## What it does, honestly

Measured on `fixtures/structured_page.png`, whose text is known:

| | Result |
| --- | --- |
| In-distribution word crops (its own training set) | **24/24 exact**, greedy and beam alike |
| A real printed page, character error rate | **~51%** (greedy), ~53% (beam) |
| Speed | ~4.3s for a 47-word page, CPU |

Those two numbers together are the whole story. **The wiring is correct** — the
preprocessing, the charset ordering and both decoders reproduce the model's own
training results exactly. **The model is the limit.** Everything the engine gets
wrong on a real page, it gets wrong because of what it was trained on, not
because of the code around it.

`test_crnn.py` asserts the first row so that distinction keeps holding: if the
in-distribution test ever fails, something in the pipeline broke, and no amount
of retraining will explain it.

## Two hard ceilings

**The charset is lowercase `a`–`z`.** Twenty-six classes plus the CTC blank.
Digits, punctuation, capitals and spaces have no output symbol, so "Unit 4"
cannot come back as "Unit 4" — not poorly, but *at all*. Roughly a fifth of an
ordinary page is unrepresentable before recognition even starts. Fixing this
means a new output layer, which means retraining from scratch.

**It was trained on ~90 synthetic words** rendered from system fonts with
affine and blur augmentation. Its own README reports ~27% character error rate
on held-out words from that vocabulary. A real page is a different font, an open
vocabulary and real ink, so ~51% is about what the training setup predicts.

## Why the default decoder is greedy

Beam search is implemented (`beam_search_decode`) and is the textbook upgrade
over greedy CTC decoding. It is not the default, because measurement disagreed
with the textbook here: **50.7% CER greedy, 52.6% beam**, and on in-distribution
crops the two agree exactly.

That is not a bug — it is what beam search does to a model that is *confidently
wrong* rather than uncertain. Greedy takes the most likely symbol per step; beam
explores alternatives weighted by the same miscalibrated probabilities and
finds a likelier wrong answer. Beam search pays off once the probability mass is
spread sensibly, which is a property of a better-trained model.

So: keep `CRNN_DECODER=greedy` until the model is retrained, then re-measure with
`scripts/eval_crnn.py` and expect beam to overtake it. A dictionary-constrained
beam (rescoring against a word list) would help more than a wider beam.

## What would actually make it good

In rough order of payoff per hour:

1. **Retrain on IAM** with a charset covering digits, punctuation and capitals.
   IAM needs manual registration, which is why it isn't automated here. This is
   the one change that moves the number.
2. **Train on lines, not words.** Line-level recognition sidesteps word
   segmentation entirely and gives the LSTM more context to work with — the
   segmentation in `detect.find_words` is decent but it is one more thing that
   can be wrong.
3. **Elastic distortion augmentation.** Simulating hand tremor generalises to
   real handwriting far better than the affine transforms used now.
4. **Dictionary-rescored beam search.** Once the model is worth searching,
   constraining beams to real words is where "etra" becomes "extra".

The engine seam means none of this changes anything outside
`app/services/ocr/crnn.py`: retrain, drop in a new `.keras` and `charset.txt`,
re-run the eval.

## Why keep it at all

It is the only engine here that runs with no network and no cost, and the
architecture around it — find the words, crop them, batch them, decode them — is
real work that a better model would inherit unchanged. At ~51% CER it is not the
engine to use for reading your notes today; `cloud_vision` is. It is the engine
that makes the offline story true rather than aspirational, and it is measured
rather than assumed.
