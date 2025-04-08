# Yosemite Valley Lodge Availability Checker
in collaboration with claude code

A Python script that automatically checks for weekend availability at Yosemite Valley Lodge and sends email notifications when rooms become available.

## Overview

This tool helps you secure accommodations at the popular Yosemite Valley Lodge by monitoring the booking website and alerting you when weekend dates become available, allowing you to book before they're gone.

## Key Features

- 🔍 Monitors Yosemite Valley Lodge booking system for weekend availability
- 📅 Prioritizes finding consecutive weekend days (Friday-Saturday or Saturday-Sunday)
- 📧 Sends detailed email notifications when rooms become available
- 🔄 Runs periodically with randomized intervals to avoid detection
- 🔒 Implements error handling and retry mechanisms for reliability

## Getting Started

### Quick Start

1. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the script once to generate a default config file:
   ```bash
   python yosemite_checker.py
   ```

3. Edit `config.json` with your email settings:
   ```json
   "email": {
       "enabled": true,
       "smtp_server": "smtp.gmail.com",
       "smtp_port": 587,
       "username": "your-email@gmail.com",
       "password": "your-app-password",
       "from_address": "your-email@gmail.com",
       "to_address": "recipient@example.com"
   }
   ```

4. Run the script continuously:
   ```bash
   python yosemite_checker.py
   ```

## Configuration Options

The script is highly configurable through the `config.json` file:

- Choose between Selenium browser automation or lightweight Requests approach
- Set how many months ahead to check for availability
- Configure check frequency and randomization
- Customize email notification settings
- Set retry parameters for reliability

## Documentation

For detailed setup instructions, deployment options, and customization guidance, see the [full documentation](utils/README.md).

## Requirements

- Python 3.7+
- Internet connection
- SMTP server access for sending email notifications

## License

This project is licensed under the MIT License.

## Disclaimer

This tool is intended for personal use only. Please use responsibly and in accordance with the terms of service of the Yosemite booking website.
