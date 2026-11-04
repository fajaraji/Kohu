# Submission text (draft for the Representative)

Draft only. Nothing has been submitted. Edit freely before pasting into the hackathon form.

## Project name

Kohu

## One line

Ask what your company knows and what it has paid for, with every answer cited to the page, cell or video second.

## Description

Know-how in a company sits on a few laptops and in a few heads, and the rest is scattered across documents, slides, sheets and screen recordings. New hires have nowhere obvious to learn how a process works. Companies buy data under licenses that cover everyone, yet only a few people know it exists. Our team has seen this problem firsthand. Atlassian's State of Teams 2025 survey of about 12,000 knowledge workers found that teams lose 25% of their time searching for answers.

Kohu is one place to search and ask. Muse Spark decides what to search and read, using tools that only ever see the sources the person's role and the company's licenses allow. The final answer is checked on the server, so every sentence with a number must match the passage it cites. Each citation opens the exact page, spreadsheet cell, slide, or the second in a screen recording where the step happens, with the button marked by SAM 3.1.

Kohu turns a screen recording into a guide. Muse Voice Transcribe writes down the narration with timings, Muse Spark watches the video with the transcript and returns timed steps, and SAM 3.1 marks the control each step uses. A reason is kept only when the narrator actually said it. A person reviews the steps before anyone can cite them.

Kohu also notices when two sources disagree. Muse Spark compares related passages across sources and flags factual contradictions. A data steward decides which source is right, the losing passage is ranked lower, and the next answer changes. A license card shows how many people actually used the data the company paid for.

## How we used Meta models

Muse Spark 1.3 runs the tool loop, writes the final answer with a JSON schema, reads scanned and chart pages, turns video into steps in background mode, proposes boxes for SAM, judges conflicts, and reads chart crops. Muse Voice Transcribe 1.0 transcribes video narration with turn times. SAM 3.1 marks controls in video frames with box prompts and finds charts and tables on report pages with noun phrases. No other AI models are used in the app.

## What we measured

On 20 frozen questions across four roles, 19 or 20 passed in each of three runs. A leak test of 74 checks across every role, tool and route found no leaks. Two of three planted conflicts were caught, and none of three control pairs was flagged. On the recording we tuned on, all nine steps were found within 0.22 seconds at the median and every SAM mark landed on the right control. On a second recording made after tuning, four of five steps were found and marked correctly. The corpus is small, so these numbers show the pipeline working rather than proving it at scale. Full numbers and failures are in docs/eval-result.md.

## Data

Company documents are pages from PostHog's public handbook, used under its MIT-style license for its contents folder. PostHog does not endorse Kohu. Purchased data is simulated with World Bank data (CC BY 4.0), and the vendor and license terms are simulated and labeled. The slide deck, performance sheet, refund process, back office app and its narrated recording are simulated and labeled.

## Links

Repository and video links are filled in by the Representative.
