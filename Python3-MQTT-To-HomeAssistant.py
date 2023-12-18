#!/usr/bin/python3

import subprocess
import argparse
import configparser
import os
import logging
import datetime
import glob
import paho.mqtt.client as mqtt

class CustomLogger(logging.Logger):
    def __init__(self, name, log_filename):
        super().__init__(name)

        # Set up formatter for log messages
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # Set up log file handler
        file_handler = logging.FileHandler(log_filename)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        self.addHandler(file_handler)

        # Set up console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.addHandler(console_handler)
        
def setup_logger(log_folder, log_date):
    global err_filepath  # Use the global variable
    log_filename = f"MQTT-To-HomeAssistant-Date{log_date}.log"
    log_filepath = os.path.join(log_folder, log_filename)

    # Set up logger for normal output
    logger = CustomLogger("MQTT-To-HomeAssistant-Date", log_filepath)

    # Set the logger level
    logger.setLevel(logging.DEBUG)

    # Set up logger for errors
    err_filename = f"MQTT-To-HomeAssistant-Date{log_date}.err"
    err_filepath = os.path.join(log_folder, err_filename)
    error_logger = CustomLogger("MQTT-To-HomeAssistant-Date-Error", err_filepath)

    # Set the error logger level
    error_logger.setLevel(logging.ERROR)

    return logger, error_logger

def mqtt_connect(client, userdata, flags, rc, mqtt_topic, mqtt_message, logger, error_logger):
    try:
        if rc == 0:
            logger.info('')
            logger.info('----------')
            logger.info('')
            logger.info('Publishing Topic and Message to MQTT')

            # Publish the message after connecting
            client.publish(mqtt_topic, mqtt_message, retain=True)

            # Disconnect from the MQTT broker
            client.disconnect()
        
        else:
            raise Exception('Failed publishing message to MQTT')
    
    except Exception as e:
        # Handle the exception and capture the error message
        error_message = str(e)
        logger.error('')
        logger.error('----------')
        logger.error('')
        logger.error('MQTT Error message: ' + error_message)
        raise Exception('Failed publishing message to MQTT')

def get_newest_files(log_dir, prefix):
    files = glob.glob(os.path.join(log_dir, f"{prefix}*"))
    files.sort(key=os.path.getctime, reverse=True)
    
    newest_log = None
    newest_err = None

    for file in files:
        ext = os.path.splitext(file)[-1][1:]  # Get the file extension without the dot
        if ext == "log" and not newest_log:
            newest_log = file
        elif ext == "err" and not newest_err:
            newest_err = file
        
        if newest_log and newest_err:
            break

# This is is for the send mail part
def send_mail(subject, body, recipient, attachment_files=None):
    mail_command = ['mail', '-s', subject, recipient]

    if attachment_files:
        for file in attachment_files:
            mail_command.extend(['--attach', file])
    print("Mail command : ", mail_command)
    process = subprocess.Popen(mail_command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    _, stderr_output = process.communicate(input=body.encode())

    mail_exit_code = process.returncode

    return mail_exit_code, stderr_output.decode().strip()

# This is for the send mail function
# In case one needs to be notified of errors
#
# FIx and make sure to make it possible to send error message even if .out file is not created yet
def MailTo(logger, error_logger, recipient):
    log_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    
    print_separator(logger)

    logger.info('There is an option to send a mail')

    # Define subject
    subject = "Error snapshotting or cleaning up snapshots/logs - attaching logs"

    # Get the latest .log and .err files
    newest_log, newest_err = get_newest_files(log_folder, "SnapBeforeWatchTower")
    attachment_files = []
    
    # Start by creating an empty body
    body = ""
    
    # Add the latest .log and .err files to the attachment list
    if newest_log:
        attachment_files.append(newest_log)
    if newest_err:
        attachment_files.append(newest_err)

     # Read contents of .err file
    if os.path.isfile(newest_err):
        with open(newest_err, 'r') as err_file:
            err_contents = err_file.read()
            body += "----------\n\n.err file\n" + err_contents

    # Read contents of .log file
    if os.path.isfile(newest_log):
        with open(newest_log, 'r') as log_file:
            log_contents = log_file.read()
            body += "----------\n\n.log file\n" + log_contents

    # Send the Mail
    mail_exit_code, stderr_output = send_mail(subject, body, recipient, attachment_files)
                
    if mail_exit_code == 0:
        WasMailSent(logger, error_logger, 0, "")
    else:
        WasMailSent(logger, error_logger, mail_exit_code, stderr_output)

def WasMailSent(logger, error_logger, MailExitCode, popenstderr):
    if MailExitCode == 0:
        print_separator(logger)
        logger.info('Mail was send succesfully')
    else:
        print_separator(logger, error_logger)
        error_logger.error('There was an error sending the mail')
        error_logger.error('This is what popen said')
        error_logger.error('')
        error_logger.error(popenstderr)
        error_logger.error('')
        error_logger.error('----------')

def print_separator(logger, error_logger=None):
    separator_length = 20
    separator = "\n" + "\n" + "-" * separator_length + "\n"
    
    if error_logger:
        error_logger.error(separator)
    else:
        logger.info(separator)

def main():
    global err_filepath  # Use the global variable
    parser = argparse.ArgumentParser(description='Send a message to HomeAssistant with MQTT')
    parser.add_argument('-c', '--config', required=True, help='Command: Location for config file')
    
    args = parser.parse_args()

    config = configparser.RawConfigParser()
    config.read(args.conf)

    # This is for creating the Date format for the Log Files
    DateTime = config.get('MQTT-To-HomeAssistant', 'DateTime')
    log_date  = datetime.datetime.now().strftime(DateTime)

    # This is for the logfile creation
    log_folder=config.get('MQTT-To-HomeAssistant', 'LogDestination')

    # This is to get the mail or "No" option for mail
    MailOption = (config.get('MQTT-To-HomeAssistant', 'Mail'))

    # This is for the command after the script has succesfully run
    SystemAction = (config.get('MQTT-To-HomeAssistant', 'SystemAction'))

    # Check if it is for homeassistant
    Use_HomeAssistant = (config.get('MQTT-To-HomeAssistant', 'Use_HomeAssistant'))

    # Origional Log creation from SnapBeforeWatchTower.py
    #log_date = datetime.datetime.now().strftime('%Y-%m-%d_%H_%M_%S')
    #log_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

    os.makedirs(log_folder, exist_ok=True)

    # Create separate loggers for main logs and error logs
    logger, error_logger = setup_logger(log_folder, log_date)

    try:
        # Your MQTT logic here
        mqtt_topic = config.get('MQTT-To-HomeAssistant', 'mqtt_topic')
        mqtt_message = config.get('MQTT-To-HomeAssistant', 'mqtt_message')
        broker_address = config.get('MQTT-To-HomeAssistant', 'broker_address')
        broker_port = config.get('MQTT-To-HomeAssistant', 'broker_port')
        broker_port = int(broker_port)
        mqtt_username = config.get('MQTT-To-HomeAssistant', 'mqtt_username')
        mqtt_password = config.get('MQTT-To-HomeAssistant', 'mqtt_password')

            # Create MQTT client instance
        client = mqtt.Client()
        client.enable_logger(logging.getLogger("paho"))
        client.username_pw_set(mqtt_username, mqtt_password)
        client.on_connect = lambda client, userdata, flags, rc: mqtt_connect(client, userdata, flags, rc, mqtt_topic, mqtt_message, logger, error_logger)

        try:
            # Attempt to connect to the MQTT broker
            client.connect(broker_address, broker_port)
        except OSError as e:
            # Handle the specific error [Errno 113] No route to host
            if e.errno == 113:
                logging.error('MQTT server is not reachable. Check IP and Port.')
                # Add your specific error handling code here
            else:
                logging.error(f'Failed to connect to MQTT broker: {str(e)}')
            raise Exception('Failed publishing message to MQTT')

        # Optionally, send a message if HomeAssistant is an option
        if Use_HomeAssistant.upper == "YES":
            homeassistant_topic = config.get('MQTT-To-HomeAssistant', 'HomeAssistant_Available')
            homeassistant_message = "online"
            client.publish(homeassistant_topic, homeassistant_message, retain=True)

        # Publish a normal message
        client.publish(mqtt_topic, mqtt_message, retain=True)

        # Start the MQTT network loop
        client.loop_forever()

        # Decide if there is an option to send mail
        if not MailOption.upper() == "NO":
            MailTo(0)

        # Decide if there is a shutdown action for the system on succesfull comletion
        if not SystemAction.upper() == "NO":
            SystemAction()

    except Exception as e:
        print_separator(logger, error_logger)
        error_logger.exception("An error occurred:")
        print_separator(logger, error_logger)
        if not MailOption.upper() == "NO":
            MailTo(logger, error_logger, args.send_mail)

    finally:
        # Check if the .err file is empty, and remove it if it is
        if os.path.exists(err_filepath) and os.path.getsize(err_filepath) == 0:
            os.remove(err_filepath)

if __name__ == "__main__":
    main()