import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from xmlrpc.client import Boolean


class Email:
    def __init__(self, gmail_sender: str, gmail_pw: str, gmail_receiver: str):
        self.gmail_sender = gmail_sender
        self.gmail_pw = gmail_pw
        self.gmail_receiver = gmail_receiver

    def send(self, subject: str, body: str) -> Boolean:
        if not self.gmail_sender or not self.gmail_pw or not self.gmail_receiver:
            return False
        message = MIMEMultipart()
        message["From"] = self.gmail_sender
        message["To"] = self.gmail_receiver
        message["Subject"] = subject
        message.attach(MIMEText(body, 'html'))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(self.gmail_sender, self.gmail_pw)
            server.send_message(message)

        return True
