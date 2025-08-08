import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

def send_verification_email(email: str, token: str):
    """ส่งอีเมลยืนยันบัญชี"""
    msg = MIMEMultipart()
    msg['From'] = f"ECP Air Quality <{os.getenv('EMAIL')}>"
    msg['To'] = email
    msg['Subject'] = "กรุณายืนยันอีเมลของคุณ"

    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f9; margin: 0; padding: 0;">
        <div style="width: 100%; max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);">
            <h1 style="color: #4CAF50; text-align: center;">ยืนยันอีเมลของคุณ</h1>
            <p style="color: #333333; font-size: 16px; line-height: 1.5; text-align: center;">สวัสดี,</p>
            <p style="color: #333333; font-size: 16px; line-height: 1.5; text-align: center;">กรุณาคลิกลิงก์ด้านล่างเพื่อยืนยันอีเมลของคุณและเริ่มใช้งานระบบ:</p>
            <a href="http://localhost:3000//email-verified?token={token}"
                style="display: block; 
                      padding: 12px 40px; 
                      background-color: #53CDFF; 
                      color: #ffffff; 
                      text-decoration: none; 
                      border-radius: 50px; 
                      text-align: center; 
                      font-weight: bold; 
                      margin-top: 20px; 
                      margin-left: auto; 
                      margin-right: auto; 
                      font-size: 16px; 
                      box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2); 
                      transition: all 0.3s ease-in-out;
                      text-transform: uppercase;
                      letter-spacing: 1px;
                      border: 2px solid #53CDFF;
                      max-width: 250px;
                      width: 100%;
                      cursor: pointer;">ยืนยันอีเมล</a>
        </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(body, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(os.getenv("EMAIL"), os.getenv("EMAIL_PASSWORD"))
        server.sendmail(os.getenv("EMAIL"), email, msg.as_string())
        server.quit()
        print("Verification email sent successfully!")
    except Exception as e:
        print(f"Error sending verification email: {e}")

def send_reset_email(email: str, token: str):
    """ส่งอีเมลรีเซ็ตรหัสผ่าน"""
    msg = MIMEMultipart()
    msg['From'] = f"ECP Air Quality <{os.getenv('EMAIL')}>"
    msg['To'] = email
    msg['Subject'] = "ลิงก์รีเซ็ตรหัสผ่าน"

    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f9; margin: 0; padding: 0;">
        <div style="width: 100%; max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);">
            <h1 style="color: #4CAF50; text-align: center;">รีเซ็ตรหัสผ่านของคุณ</h1>
            <p style="color: #333333; font-size: 16px; line-height: 1.5; text-align: center;">สวัสดี,</p>
            <p style="color: #333333; font-size: 16px; line-height: 1.5; text-align: center;">กรุณาคลิกลิงก์ด้านล่างเพื่อรีเซ็ตรหัสผ่านของคุณ:</p>
            <a href="http://localhost:3000//reset-password?token={token}"
                style="display: block; 
                      padding: 12px 40px; 
                      background-color: #53CDFF; 
                      color: #ffffff; 
                      text-decoration: none; 
                      border-radius: 50px; 
                      text-align: center; 
                      font-weight: bold; 
                      margin-top: 20px; 
                      margin-left: auto; 
                      margin-right: auto; 
                      font-size: 16px; 
                      box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2); 
                      transition: all 0.3s ease-in-out;
                      text-transform: uppercase;
                      letter-spacing: 1px;
                      border: 2px solid #53CDFF;
                      max-width: 250px;
                      width: 100%;
                      cursor: pointer;">รีเซ็ตรหัสผ่าน</a>
        </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(body, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(os.getenv("EMAIL"), os.getenv("EMAIL_PASSWORD"))
        server.sendmail(os.getenv("EMAIL"), email, msg.as_string())
        server.quit()
        print("Reset email sent successfully!")
    except smtplib.SMTPAuthenticationError as auth_error:
        print(f"Authentication Error: {auth_error}")
    except smtplib.SMTPException as e:
        print(f"SMTP Error: {e}")
    except Exception as e:
        print(f"Error sending reset email: {e}")