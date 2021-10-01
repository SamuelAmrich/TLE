#!/usr/bin/python
import smtplib, ssl
# import time 
# time.sleep(10)
smtp_server = "smtp.gmail.com"
sender_email = "ikozmos99@gmail.com"
receiver_email = "samuel.amrich@gmail.com" 
password = "to to je heslo"
message = "Subject: Raspberry pi - Kolonica - Reboot RPi."
port = 465

context = ssl.create_default_context()
with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
    server.login(sender_email, password)
    server.sendmail(sender_email, receiver_email, message)
