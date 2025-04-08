# Yosemite Valley Lodge Availability Checker

A Python script that monitors Yosemite Valley Lodge for weekend availability and sends email notifications when rooms become available.

## Features

- Checks for weekend availability at Yosemite Valley Lodge (Friday-Saturday or Saturday-Sunday pairs)
- Looks ahead for the next 6 months by default
- Sends email notifications when rooms become available
- Supports two methods:
  - Selenium-based browser automation
  - Requests/BeautifulSoup for lightweight checking
- Runs periodically with randomized intervals
- Includes error handling, logging, and retry mechanisms

## Setup Instructions

### Prerequisites

- Python 3.7 or higher
- pip (Python package manager)

### Installation

1. Clone or download this repository
2. Install required packages:

```bash
pip install selenium webdriver-manager requests beautifulsoup4
```

3. Edit the configuration file (`config.json`):
   - The first time you run the script, it will create a default configuration file
   - Update the email settings with your SMTP server details
   - Adjust other settings as needed

### Configuration Options

Key settings in `config.json`:

- `method`: Choose between "selenium" or "requests" approaches
- `browser`: Choose "chrome" or "firefox" (for selenium method)
- `headless`: Run browser in headless mode (no GUI)
- `check_interval_hours`: Hours between availability checks
- `months_ahead`: How many months in advance to check
- `email`: Configuration for email notifications

## Usage

### Basic Usage

```bash
python yosemite_checker.py
```

This will run the script continuously, checking for availability at the configured interval.

### Command Line Options

- `-c, --config`: Specify a custom configuration file path
- `-s, --single-run`: Run once and exit
- `-d, --debug`: Enable debug logging

Example with options:

```bash
python yosemite_checker.py --config my_config.json --single-run --debug
```

## Deployment Options

### Running in the Background

#### Linux/macOS

Use nohup to run the script in the background:

```bash
nohup python yosemite_checker.py > yosemite.log 2>&1 &
```

#### Windows

Create a batch file (run_checker.bat):

```
@echo off
start /B pythonw yosemite_checker.py
```

### Scheduling with Cron (Linux/macOS)

Set up a cron job to run the script regularly:

```bash
crontab -e
```

Add a line like:

```
0 */6 * * * cd /path/to/script && python yosemite_checker.py --single-run
```

### Using Docker

A Dockerfile is provided to containerize the application:

```bash
docker build -t yosemite-checker .
docker run -d --name yosemite-checker yosemite-checker
```

## Customization

### Monitoring Different Lodges

- Modify the URLs in the configuration
- Adjust the Selenium or Requests methods to handle different booking systems

### Notification Options

- The script currently supports email notifications
- You can extend it to support other notification methods like SMS or push notifications

## Troubleshooting

- Check the log file (`yosemite_checker.log`) for error messages
- Make sure your SMTP settings are correct
- For Selenium issues, try running without headless mode to see what's happening
- Increase the retry values if the website is slow to respond

## License

This project is licensed under the MIT License - see the LICENSE file for details.