# Submission text (ready to paste)

Nothing has been submitted. The Representative pastes these into the hackathon form and posts. Fill in the video link and the hosted URL where marked.

## Form

**Which problem statement did you build towards?** Build for Your World

**Project Description**

Kohu is one place to ask what a company knows and what it has paid for. Know-how sits on a few laptops and in a few heads, and the rest is spread across documents, slides, sheets and screen recordings. Atlassian's State of Teams 2025 survey of about 12,000 knowledge workers found that teams lose 25% of their time searching for answers.

You sign in as a role and ask in plain words. Kohu searches only what that role and the company's licenses allow, and every sentence cites its source down to the page, the spreadsheet cell, the slide, or the second in a screen recording, with the button to click marked on the frame. When two sources disagree, Kohu shows both and a data admin decides which one is right, and the next answer changes. A screen recording becomes a reviewed step by step guide. A license card shows who actually used the data the company paid for.

On 20 frozen questions run five times, 96 of 100 answers passed, and 74 access checks found no leaks. Live demo: <hosted URL>

**Public GitHub Repository** https://github.com/fajaraji/Kohu

**3-Minute Demo Video** <YouTube link>

**Describe your use of Meta products to build the submitted project**

Every AI feature in Kohu runs on the Meta Model API, and no other AI model is used.

Muse Spark 1.3 runs the agent. It picks search and read tools through function calling, and those tools only return sources the asker may see. It writes the final answer with a JSON schema, and the server rejects any citation or number that the cited passage does not contain. Muse Spark also reads scanned and chart pages from images, judges whether two passages contradict each other, and watches a screen recording (Files API video input, background mode with polling) together with its transcript to return timed steps.

Muse Voice Transcribe 1.0 writes down the narration of each recording with turn start and end times, so a step can be cited to the second and a reason is kept only when the narrator said it.

SAM 3.1 marks the control each step uses in the video frame, refining a box that Muse Spark proposes, and finds charts and tables on report pages before Muse Spark reads them. Masks are decoded with Meta's meta-sam-parser.

**Why are Meta's models important to your solution?**

Kohu's promise is that every answer can be checked at its source, and that needs three kinds of understanding working together. Muse Spark understands text, images and video in one model, so the same agent can read a policy page, a chart and a screen recording. Muse Voice Transcribe gives the timings that turn a recording into citations to the second. SAM 3.1 shows the exact button or chart on screen instead of describing it. Having all three behind one API and one key let a two person team build the full loop from question to cited, marked answer in days.

**Provide feedback from your experience using partner technologies** We did not use Fireworks, Modal or Baseten. (Leave blank, or paste this sentence.)

**Rating questions.** These are the team's own opinion, so pick them yourself. Notes from the build, to help you choose:

- The API worked reliably once the key was set up. The first calls returned 403 until the key was attached correctly.
- Background mode with polling handled one minute videos without timeouts.
- SAM 3.1 output needs Meta's meta-sam-parser to decode masks. Our own parsing matched it on every pixel, but the format is not obvious without the package.
- We did not use Muse Code, so that question can be left blank.

## YouTube

**Title** (pick one)

1. Your company already paid for the answer. Kohu finds it.
2. Ask your company anything and get the page, the cell, or the second
3. Kohu turns company documents and screen recordings into cited answers

**Description**

Your company already knows the answer. It is in a PDF nobody opens, a spreadsheet only analysts can see, or a screen recording from two years ago. Kohu finds it and shows you exactly where it came from.

Sign in as a role, ask in plain words, and every sentence comes back with a source. Click it and you land on the page, the spreadsheet cell, the slide, or the second in a screen recording, with the button to click marked on the frame.

What you see in this demo
0:00 The problem
0:17 A new hire asks how to process a refund
0:44 An answer from data the company already paid for
0:57 Same question, four roles, different answers
1:11 Two sources disagree and a data admin decides
1:30 A screen recording becomes a step by step guide
1:49 Who used the paid data, and what we measured

Built for the Meta hackathon with Muse Spark 1.3, Muse Voice Transcribe 1.0 and SAM 3.1. All AI in Kohu runs on Meta models.

Measured on 20 frozen questions run five times. 96 of 100 answers passed and 74 access checks found no leaks. Every failure is listed in the repo.

Code: https://github.com/fajaraji/Kohu
Live demo: <hosted URL>

Company documents are pages from PostHog's public handbook (MIT style license, no endorsement). Purchased data is World Bank data (CC BY 4.0) with a simulated vendor. The company, its back office app and the recordings are simulated. Narration is a synthetic voice and waiting time is sped up and labeled.

## X (thread, attach the video to the first post)

**1/**
Your company already paid for the answer.

It is in a PDF nobody opens, a sheet only analysts can see, or a screen recording from two years ago.

We built Kohu to find it and show you the exact page, cell, or second. 🧵

**2/**
Ask in plain words. Every sentence cites its source.

Click a citation and the screen recording jumps to the second where the step happens, with the button marked on the frame by SAM 3.1.

**3/**
Not everyone should see everything.

A new hire, an analyst and a manager ask the same question. Each gets only what their role and the company's licenses allow, and nobody is told what is hidden.

**4/**
When two sources disagree, Kohu does not guess.

It shows both. A data admin picks the right one, and every answer after that changes.

**5/**
We measured it. 96 of 100 answers passed over five runs, and 74 access checks found no leaks. The failures are in the repo too.

Muse Spark, Muse Voice Transcribe and SAM 3.1 on the Meta Model API.

Code: github.com/fajaraji/Kohu
Try it: <hosted URL>

Before posting, check the hackathon rules for a required hashtag or account to tag, and add it to the first post.
