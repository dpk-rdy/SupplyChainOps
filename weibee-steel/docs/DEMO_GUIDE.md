# Demo guide: showing this on a call

A 15-minute walkthrough for a non-technical audience, with a 5-minute version, the questions you are
likely to get, and what to do if the technology misbehaves.

## Before the call (10 minutes)

1. Run `make run` once so `output/bid_intelligence_report.html` is fresh, then open it in a browser tab.
   If you cannot run it, open `docs/bid_intelligence_report.pdf` instead. Same content, no hover.
2. Open `docs/images/` in a second tab in case screen share drops.
3. Have `output/pipeline_scorecard.csv` open in Excel or Sheets. Executives like seeing it is a plain spreadsheet.
4. Zoom the browser to 110 to 125 % so the tiles and tables are readable over screen share.
5. Decide which two findings you will tell as stories. Do not read all seven.

## The 15-minute walkthrough

**0:00 Frame it (1 minute).** Say what it is and what it is not.

> "This is a working version of the data loop in the job description: where we win, what the work
> actually earns, and which upcoming projects deserve estimating hours. The data is made up, but it
> behaves like a real shop's history. I built it to show how I think, not to tell you about your business."

**1:00 The six numbers (2 minutes).** Scroll to the tiles. Read them left to right in one sentence each.
Pause on two: *"Margin we estimated but did not keep"* and *"How full the shop looks"*. Those are the
two numbers a fabricator's owner feels every month.

**3:00 Two findings as stories (4 minutes).** Scroll to Findings. Pick two:

- *Where the shop fits.* "Three project types win 37 to 41 percent and keep their margin. Three others
  win 12 to 15 percent and give back 7 to 10 points. The bottom three used 29 percent of estimating
  hours for 18 percent of the dollars. The action is not 'never bid them', it is 'bid them when a
  relationship GC asks, not on a hard bid'."
- *Price shoppers.* "Seven GCs award us 18 percent of what we price for them and we are 11 percent
  high when we lose. Four A-class accounts returned 29 million on fewer hours. That is a conversation
  about where the estimating team's week goes."

Say once: "Every sentence here is computed from the data. If the numbers change, the sentences change."

**7:00 The scorecard (4 minutes).** Scroll to Bid / no-bid. Show the summary first (how many Pursue,
Review, Pass and the hours). Then the ranked table. Pick one Pursue row and one Pass row and read the
*Why* column aloud. Then:

> "This is the Monday-morning tool. It is a starting point for the bid meeting, not a verdict. The
> room overrides it, and we log the override, so next quarter the model has learned from the room."

Hover over a bar in the hit-rate chart or the capacity chart to show the detail is one hover away.

**11:00 Capacity (2 minutes).** Show the shop-load chart. "Blue is won work, amber is what we are
chasing counted at its odds, the dashed line is what the shop can do. After the first quarter of next
year the shop is half empty unless the pipeline converts. That is the business-development target
in tons, not in vibes."

**13:00 Trust and next steps (2 minutes).** Scroll to "How much to trust the win odds". One sentence:
"Tested on bids it had never seen, it is clearly better than guessing and clearly not perfect. Good
enough to rank; not good enough to overrule a person on one job." Then close with the 90-day plan
from `docs/memo.md`: intake first, marts second, scorecard third.

## The 5-minute version

Tiles (1 min), one finding (1.5 min), the scorecard summary and one row (2 min), one closing line
about trust (0.5 min). Skip the charts entirely; offer to send the PDF.

## Questions you will get, and short answers

| Question | Answer |
|---|---|
| Is this our data? | No. It is generated to behave like a mid-size fabricator's history. The point is the pipeline and the decision logic, which would run unchanged on real data. |
| What would you need from us? | The fields in `docs/data_dictionary.md`: the bid log, job-cost closes and a GC list. Most shops already have them in three places. |
| How long to get it running on our numbers? | Weeks, not months, if the bid log exists. The slow part is backfilling lost reasons and the low-bid numbers, which is a phone-call job, not a software job. |
| Is this AI? | The win odds come from a small statistical model fitted to our own bids. It is the kind of math an insurance company uses, not a chatbot. AI-assisted takeoff is a separate, later question, and this gives us the data to judge whether it pays. |
| Can we trust the win odds? | Enough to rank and to budget estimating hours. Not enough to skip a job the room believes in. The report says that in its own words. |
| What if the estimators disagree with it? | Good. The override is logged and becomes training data. The tool should earn their trust, not replace their judgement. |
| Who owns this? | The Business Development role. Estimating supplies hours and results, PM and accounting supply job cost, BD owns the database and the weekly scorecard. |
| What does it cost to run? | Python and a free database. No licences. One afternoon a quarter to re-fit and review. |

## If the technology misbehaves

- Screen share fails: send `docs/bid_intelligence_report.pdf` in the chat and talk them through it by page.
- Browser will not open the HTML: the PDF has every section; only the hover detail is lost.
- Someone asks for the raw data: `output/data/` has the five generated tables as CSV.
- Someone asks to see the code: `bid_intelligence/sql/` is readable SQL, one file per table, and
  `bid_intelligence/scorecard.py` has the recommendation rules in plain `if` statements. Show those,
  not the model code.

## One-line summary to leave them with

"Every bid we send teaches us something. Right now that lesson lives in people's heads. This puts it
in a table, turns it into a ranked list every Monday, and tells us how full the shop will be next year."
