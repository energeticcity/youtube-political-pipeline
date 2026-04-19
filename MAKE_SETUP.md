# Make.com setup — auto-post to Instagram + YouTube

Two scenarios, both consume the RSS feed at:
```
https://raw.githubusercontent.com/energeticcity/youtube-political-pipeline/main/feed.xml
```

Each scenario polls the feed every 15 min, detects new dad joke entries, and posts to one platform. Free Make.com plan covers both (~360 ops/month total, well under the 1,000 free).

---

## Prerequisites

- [ ] Make.com free account (sign up at [make.com](https://www.make.com))
- [ ] Instagram **Creator** or **Business** account (NOT personal — see README for conversion)
- [ ] Facebook Page linked to your Instagram account
- [ ] YouTube channel for Dad Joke Fix (existing or new)
- [ ] Google account that owns the YouTube channel

---

## Scenario 1: RSS → Instagram Reel

### Step 1: Create the scenario
1. Make.com dashboard → **Create a new scenario**
2. Name it: `Dad Joke Fix → Instagram`

### Step 2: Add the RSS trigger
1. Click the big `+` to add the first module
2. Search **RSS** → pick **Watch RSS feed items**
3. Click **Create a connection** → name it `Dad Joke Fix Feed` → Save
4. Configure:
   - **URL**: `https://raw.githubusercontent.com/energeticcity/youtube-political-pipeline/main/feed.xml`
   - **Maximum number of returned items**: `1`
   - Leave other fields default
5. Click **OK**
6. Right-click the module → **Choose where to start** → **From now on** (so it doesn't repost old items)

### Step 3: Add the Instagram module
1. Click the `+` to add the next module
2. Search **Instagram for Business** → pick **Create a Photo or Reel**
3. Click **Create a connection**:
   - You'll be redirected to Facebook to authorize
   - Sign in with the Facebook account that owns the Page linked to your IG
   - Grant all permissions when prompted (especially `instagram_content_publish`)
   - Return to Make.com
4. Configure the module:
   - **Method**: `Reels`
   - **Page**: select your Facebook Page (e.g. "Dad Joke Fix")
   - **Video URL**: click in the field → in the popup, navigate to the RSS module output → select **Enclosure → URL** (this is why we added the `<enclosure>` tag)
   - **Caption**: click → select **Description** from the RSS module
   - **Share to feed**: `Yes`
5. Click **OK**

### Step 4: Set the schedule
1. Click the clock icon at the bottom-left of the scenario canvas
2. **Run scenario**: `At regular intervals`
3. **Minutes**: `15`
4. Click **OK**

### Step 5: Activate
1. Toggle the switch at the bottom-left from OFF to **ON**
2. Done — every 15 min, Make checks for new joke; posts the next one to Instagram automatically

---

## Scenario 2: RSS → YouTube Short

### Step 1: Create the scenario
1. Make.com dashboard → **Create a new scenario**
2. Name it: `Dad Joke Fix → YouTube`

### Step 2: Add the RSS trigger
1. `+` → **RSS** → **Watch RSS feed items**
2. Click **Add** for connection → select the existing `Dad Joke Fix Feed` connection (reuse it)
3. Same config as before:
   - **URL**: `https://raw.githubusercontent.com/energeticcity/youtube-political-pipeline/main/feed.xml`
   - **Maximum number of returned items**: `1`
4. Click **OK**
5. Right-click → **Choose where to start** → **From now on**

### Step 3: Download the video file
YouTube needs the actual file, not a URL.
1. `+` → **HTTP** → **Get a file**
2. Configure:
   - **URL**: click → select **Enclosure → URL** from the RSS module
   - **Method**: `GET`
3. Click **OK**

### Step 4: Add the YouTube upload module
1. `+` → **YouTube** → **Upload a Video**
2. Click **Create a connection**:
   - Sign in with the Google account that owns your YouTube channel
   - Grant all YouTube permissions
   - Return to Make.com
3. Configure the module:
   - **Title**: click → select **Title** from the RSS module
   - **Description**: click → select **Description** from the RSS module
   - **Privacy status**: `Public`
   - **Category**: `Comedy`
   - **Tags**: `dadjokes,dadjoke,dadjokefix,comedy,shorts,funny,jokes`
   - **Source file**: 
     - **File name**: type `dadjoke.mp4`
     - **Data**: click → select **Data** from the HTTP "Get a file" module
4. Click **OK**

### Step 5: Set the schedule
1. Clock icon → `At regular intervals` → `15` minutes
2. Click **OK**

### Step 6: Activate
1. Toggle ON at bottom-left
2. Done

---

## Testing

After activating both scenarios:

1. **Trigger a pipeline run manually**: GitHub → Actions → Daily Dad Joke Pipeline → Run workflow
2. Wait ~3 min for the pipeline to complete and update the RSS feed
3. Within 15 min of feed update, Make.com will detect the new item and post to both platforms
4. Watch your Instagram and YouTube channels for the new post
5. Check Make.com → Scenarios → click each scenario → see the run history (green checkmarks = success)

---

## Cost (Make.com operations)

| Action | Ops per run |
|---|---|
| RSS check (no new item) | 1 |
| RSS check (new item found) + IG post | 2 |
| RSS check (new item found) + HTTP download + YouTube upload | 3 |

At 2 jokes/day:
- IG scenario: ~96 ops/day × 30 = ~2,900 ops/month if always polling
- Wait — polling 96/day × 30 = 2,880 RSS checks. **This exceeds the free tier (1,000 ops/month).**

**Fix**: extend the scheduling interval to **1 hour instead of 15 min**:
- 24 polls/day × 30 = 720 ops/month for the polls
- + 60 actual posts × ~3 ops = 180 ops/month
- = **~900 ops/month total — fits in free tier ✅**

So in step 4 of each scenario, set **Minutes: `60`** instead of `15`. Posts will be delayed by up to an hour vs. the pipeline run, which is fine for dad jokes.

---

## Troubleshooting

### Instagram fails with "media_type not supported"
You're posting to a personal account. Verify it's converted to Creator/Business and linked to a Facebook Page.

### YouTube fails with "channel not found"
The Google account you connected doesn't own a YouTube channel, or owns multiple and Make picked the wrong one. Disconnect, then reconnect with the correct account selected first.

### Same joke posted twice
Make's "watch RSS" should track which items it's already seen. If duplicates happen, right-click the trigger → **Choose where to start** → **From now on** to reset.

### Make says "no new items" even after a pipeline run
Check feed.xml directly in browser — does the new item appear? If yes, Make is just on its polling cycle. Wait up to 60 min.

### Instagram fails on long captions
IG has a 2,200 character caption limit. Our descriptions are well under that, but if it ever fails, add a **Tools → Text Parser** module between RSS and IG to truncate.

---

## What this replaces

- ❌ No Publer needed (was $12/mo for RSS)
- ❌ No direct YouTube OAuth in pipeline.py (Make handles it)
- ❌ No Meta App Review needed (Make's app is already reviewed)
- ✅ Free, automatic, two platforms covered

TikTok still requires manual upload (see the auto-generated GitHub Issue after each pipeline run for the download link + caption).
