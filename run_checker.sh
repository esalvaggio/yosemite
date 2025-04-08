#!/bin/bash

# Activate virtual environment
source yosemite_env/bin/activate

# Default to single run
MODE="--single-run"

# Check if we have any arguments
if [ "$1" == "test-email" ]; then
  echo "Running in test email mode..."
  MODE="--test-email"
elif [ "$1" == "debug" ]; then
  echo "Running in debug mode..."
  MODE="--single-run --debug"
elif [ "$1" == "continuous" ]; then
  echo "Running in continuous mode..."
  MODE=""
elif [ "$1" == "update-email" ]; then
  # Get current email settings first
  EMAIL_USERNAME=$(grep -o '"username": *"[^"]*"' config.json | cut -d'"' -f4)
  
  if [ -n "$EMAIL_USERNAME" ]; then
    echo "Current email username is: $EMAIL_USERNAME"
    read -p "Do you want to update email settings? (y/n): " SHOULD_UPDATE
    if [ "$SHOULD_UPDATE" != "y" ]; then
      echo "Keeping current email settings. Running email test..."
      python yosemite_checker.py --test-email
      exit 0
    fi
  fi

  # Update email settings
  echo "Updating email settings in config.json..."
  
  echo "Enter your Gmail address: "
  read EMAIL_ADDRESS
  
  echo "Enter your app password (not your regular Gmail password): "
  read -s APP_PASSWORD
  echo ""
  
  # Create new config with jq if available, or Python as a backup
  if command -v jq >/dev/null 2>&1; then
    echo "Using jq to update configuration..."
    # Use jq to properly update the JSON
    jq --arg email "$EMAIL_ADDRESS" --arg pass "$APP_PASSWORD" '.email.username = $email | .email.password = $pass | .email.from_address = $email | .email.to_address = $email' config.json > config.json.tmp
    mv config.json.tmp config.json
  elif command -v python3 >/dev/null 2>&1; then
    echo "Using Python to update configuration..."
    # Use Python to update the JSON
    python3 -c "
import json
with open('config.json', 'r') as f:
    config = json.load(f)
config['email']['username'] = '$EMAIL_ADDRESS'
config['email']['password'] = '$APP_PASSWORD'
config['email']['from_address'] = '$EMAIL_ADDRESS'
config['email']['to_address'] = '$EMAIL_ADDRESS'
with open('config.json', 'w') as f:
    json.dump(config, f, indent=4)
"
  else
    # Fallback to manual sed replacement
    echo "Using sed to update configuration..."
    # Use temporary files to avoid sed issues on macOS
    cat config.json | sed "s/\"username\": \".*\"/\"username\": \"$EMAIL_ADDRESS\"/" > config.json.tmp
    mv config.json.tmp config.json
    
    cat config.json | sed "s/\"password\": \".*\"/\"password\": \"$APP_PASSWORD\"/" > config.json.tmp
    mv config.json.tmp config.json
    
    cat config.json | sed "s/\"from_address\": \".*\"/\"from_address\": \"$EMAIL_ADDRESS\"/" > config.json.tmp
    mv config.json.tmp config.json
    
    cat config.json | sed "s/\"to_address\": \".*\"/\"to_address\": \"$EMAIL_ADDRESS\"/" > config.json.tmp
    mv config.json.tmp config.json
  fi
  
  echo "Email settings updated. Testing email configuration..."
  python yosemite_checker.py --test-email
  exit 0
fi

echo "Starting Yosemite availability checker..."
echo "This script checks for weekend availability at Yosemite Valley Lodge."
echo "It will save screenshots of search results and send email notifications if availability is found."
echo "Run './run_checker.sh update-email' if you need to update your email credentials."
echo ""

# Run the checker script
python yosemite_checker.py $MODE

# Note: Press Ctrl+C to stop the script
