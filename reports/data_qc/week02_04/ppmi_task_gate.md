# PPMI 24-month task gate

The confirmed primary branch is candidate A (`MDS-UPDRS Part III follow-up
score minus baseline score`) with `prefer_off`. Candidate B is the
secondary/sensitivity target; `unique_only` and `prefer_on` are sensitivity
policies. Configuration status is `READY_FOR_USER_SELECTED_TASK`.

| Candidate | Policy | Independent subjects | Recommendation |
|---|---|---:|---|
| A | `unique_only` | 179 | shorter window |
| A | `prefer_off` | 151 | shorter window |
| A | `prefer_on` | 154 | shorter window |
| B | `unique_only` | 177 | shorter window |
| B | `prefer_off` | 149 | shorter window |
| B | `prefer_on` | 153 | shorter window |

All branches fall in the 120–179 range. This is an audit result, not an automatic scientific choice.

The primary branch contains 151 independent subjects at 24 months and therefore
retains the preregistered `SHORTER_WINDOW_RECOMMENDED` recommendation. This is a
scientific sample-size recommendation, not an engineering WARN or FAIL.
