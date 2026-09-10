# Benchmark

Evaluation of the triage agent against dispositions assigned by human experts
(D-013).

## Method

1. Draw a sample of candidates whose disposition is already assigned.
2. Hide the disposition. The agent must not see it, and the code path that
   fetches labels is separate from the code path that builds agent input.
3. Run triage.
4. Compare verdict to disposition: precision, recall, confusion matrix per
   class.

## What this does and does not show

It shows the agent judges as an expert would, on real data, with labels this
project did not create.

It does not show discovery. Labelled candidates have already been vetted by
someone. Discovery means pointing the system at unlabelled queues, which is
only meaningful once accuracy is established.

## Cost

These tests call a language model and cost money per run. They are marked
`@pytest.mark.benchmark` and excluded from the default suite. Run them
deliberately, on a fixed sample, and record the sample with the results.

## Before implementing

Verify against the live TOI catalog which dispositions are exposed and how they
are encoded. Do not assume the schema.
