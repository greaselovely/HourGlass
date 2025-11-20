# Google Cloud Text-to-Speech Setup

This guide walks you through setting up Google Cloud TTS for HourGlass video intros.

## Overview

Google Cloud TTS provides high-quality neural voices for natural-sounding speech. The free tier includes 1 million characters per month, which is more than enough for daily timelapse intros.

## Setup Steps

### 1. Create or Access Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Note your **Project ID** (you'll see it in the project selector)

### 2. Enable the Text-to-Speech API

1. Go to **APIs & Services > Library**
2. Search for "Cloud Text-to-Speech API"
3. Click **Enable**

### 3. Create Service Account Credentials

1. Go to **APIs & Services > Credentials**
2. Click **Create Credentials > Service Account**
3. Enter a name (e.g., "hourglass-tts")
4. Click **Create and Continue**
5. For role, you can skip or select "Cloud Text-to-Speech User"
6. Click **Done**

### 4. Generate JSON Key

1. Click on your newly created service account
2. Go to the **Keys** tab
3. Click **Add Key > Create new key**
4. Select **JSON** format
5. Click **Create**
6. Save the downloaded file as `tts.json`

### 5. Install the Credentials

Place the `tts.json` file in the HourGlass project root directory:

```
HourGlass/
  tts.json          <-- Place here
  main.py
  timelapse_core.py
  ...
```

**Important:** Do not commit `tts.json` to version control. It's already in `.gitignore`.

### 6. Install Python Dependencies

```bash
pip install google-cloud-texttospeech
```

Or install all requirements:

```bash
pip install -r requirements.txt
```

## Configuration

TTS settings are configured in your project's JSON config file under `music.tts_intro`:

```json
{
  "music": {
    "tts_intro": {
      "enabled": true,
      "voice_gender": "female",
      "rate": 150,
      "volume": 0.9
    }
  }
}
```

### Options

- **enabled**: `true` or `false` - Enable/disable TTS intro
- **voice_gender**: `"female"` or `"male"` - Voice selection
- **rate**: Speech rate in words per minute (default: 150)
- **volume**: Volume level 0.0 to 1.0 (default: 0.9)

## Voice Options

HourGlass uses Neural2 voices for best quality:

- **Female**: `en-US-Neural2-F`
- **Male**: `en-US-Neural2-D`

## Pricing

- **Free Tier**: 1 million characters per month (Neural2 voices)
- A typical intro (~50 characters) means you can generate ~20,000 intros/month for free
- At 1 video per day, you'll use less than 2% of the free tier

## Troubleshooting

### "TTS skipped: tts.json credentials file not found"

The `tts.json` file is missing from the HourGlass directory. Follow steps 3-5 above to create and install it.

### "google-cloud-texttospeech not installed"

Run:
```bash
pip install google-cloud-texttospeech
```

### API Not Enabled

If you get a "Cloud Text-to-Speech API has not been enabled" error:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **APIs & Services > Library**
3. Search for "Cloud Text-to-Speech API"
4. Click **Enable**

### Permission Denied

Ensure your service account has the "Cloud Text-to-Speech User" role or the project owner role.

## Testing

To test TTS without creating a full video:

```bash
python main.py YOUR_PROJECT --movie --cache
```

This will use cached audio and generate a TTS intro if `tts.json` is configured.
