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
        
def send_welcome_email(email: str, location: str):
    """ส่งอีเมลต้อนรับการสมัครรับการแจ้งเตือน"""
    msg = MIMEMultipart()
    msg['From'] = f"ECP Air Quality <{os.getenv('EMAIL')}>"
    msg['To'] = email
    msg['Subject'] = "ยืนยันการสมัครรับการแจ้งเตือนคุณภาพอากาศ"

    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f9; margin: 0; padding: 0;">
        <div style="width: 100%; max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);">
            <h1 style="color: #4CAF50; text-align: center;">ยินดีต้อนรับสู่ระบบแจ้งเตือนคุณภาพอากาศ</h1>
            <p style="color: #333333; font-size: 16px; line-height: 1.5; text-align: center;">สวัสดีครับ/ค่ะ!</p>
            <p style="color: #333333; font-size: 16px; line-height: 1.5; text-align: center;">ขอบคุณที่สมัครรับการแจ้งเตือนของเรา</p>
            
            <div style="background-color: #e8f5e8; padding: 15px; border-left: 4px solid #4CAF50; margin: 20px 0; border-radius: 5px;">
                <p style="margin: 0; color: #333333; font-size: 16px;"><strong>📧 อีเมลของคุณ:</strong> {email}</p>
                <p style="margin: 5px 0 0 0; color: #333333; font-size: 16px;"><strong>📍 พื้นที่ที่เลือก:</strong> {location}</p>
            </div>
            <p style="color: #333333; font-size: 16px; line-height: 1.5;"><strong>คุณจะได้รับการแจ้งเตือนค่า AQI, PM1, PM2.5, PM4, PM10, อุณหภูมิ, ความชื้น 7 โมงเช้าของวันนี้:</strong></p>
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
        print(f"Welcome email sent successfully to {email}")
        return True
    except smtplib.SMTPAuthenticationError as auth_error:
        print(f"Authentication Error: {auth_error}")
        return False
    except smtplib.SMTPException as e:
        print(f"SMTP Error: {e}")
        return False
    except Exception as e:
        print(f"Error sending welcome email: {e}")
        return False

def send_daily_aqi_email(email: str, location: str, avg_data: dict):
    """ส่งอีเมลแจ้งเตือนข้อมูลคุณภาพอากาศเฉลี่ย 7 โมงเช้า"""
    msg = MIMEMultipart()
    msg['From'] = f"ECP Air Quality <{os.getenv('EMAIL')}>"
    msg['To'] = email
    msg['Subject'] = f"แจ้งเตือนคุณภาพอากาศ ({location}) เวลา 7 โมงเช้า"

    data_rows = ""
    field_names = {
        "AQI": "ดัชนีคุณภาพอากาศ (AQI)",
        "PM1": "PM1 (μg/m³)",
        "PM2.5": "PM2.5 (μg/m³)",
        "PM4": "PM4 (μg/m³)",
        "PM10": "PM10 (μg/m³)",
        "Temperature": "อุณหภูมิ (°C)",
        "Humidity": "ความชื้น (%)"
    }
    
    for field, thai_name in field_names.items():
        value = avg_data.get(field)
        if value is not None:
            if field == "AQI":
                if value <= 50:
                    color = "#4CAF50"  # เขียว - ดี
                elif value <= 100:
                    color = "#FFC107"  # เหลือง - ปานกลาง
                elif value <= 150:
                    color = "#FF9800"  # ส้ม - มีผลกระทบต่อสุขภาพ
                elif value <= 200:
                    color = "#F44336"  # แดง - ไม่ดีต่อสุขภาพ
                else:
                    color = "#9C27B0"  # ม่วง - อันตราย
            else:
                color = "#333333"
                
            data_rows += f"""
            <tr style="border-bottom: 1px solid #e0e0e0;">
                <td style="padding: 12px; text-align: left; font-weight: bold; color: #555;">{thai_name}</td>
                <td style="padding: 12px; text-align: center; font-weight: bold; color: {color}; font-size: 18px;">{value}</td>
            </tr>
            """
        else:
            data_rows += f"""
            <tr style="border-bottom: 1px solid #e0e0e0;">
                <td style="padding: 12px; text-align: left; font-weight: bold; color: #555;">{thai_name}</td>
                <td style="padding: 12px; text-align: center; color: #999; font-style: italic;">ไม่มีข้อมูล</td>
            </tr>
            """

    body = f"""
    <html>
    <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f4f9; margin: 0; padding: 20px;">
        <div style="width: 100%; max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; box-shadow: 0 6px 20px rgba(0, 0, 0, 0.1); overflow: hidden;">
            <!-- Header -->
            <div style="background: linear-gradient(135deg, #4CAF50, #45a049); color: white; padding: 25px; text-align: center;">
                <h1 style="margin: 0; font-size: 24px; font-weight: 600;">🌍 รายงานคุณภาพอากาศ</h1>
                <p style="margin: 5px 0 0 0; font-size: 16px; opacity: 0.9;">📍 {location} | ⏰ 7:00 น.</p>
            </div>
            
            <!-- Content -->
            <div style="padding: 30px;">
                <p style="color: #333333; font-size: 16px; line-height: 1.6; margin-bottom: 25px; text-align: center;">
                    ข้อมูลคุณภาพอากาศเฉลี่ยในช่วงเวลา 7:00 น. ของวันนี้
                </p>
                
                <!-- Data Table -->
                <table style="width: 100%; border-collapse: collapse; background-color: #fafafa; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);">
                    <thead>
                        <tr style="background-color: #e8f5e8;">
                            <th style="padding: 15px; text-align: left; color: #2e7d32; font-weight: 600; font-size: 16px;">รายการ</th>
                            <th style="padding: 15px; text-align: center; color: #2e7d32; font-weight: 600; font-size: 16px;">ค่าเฉลี่ย</th>
                        </tr>
                    </thead>
                    <tbody>
                        {data_rows}
                    </tbody>
                </table>
                
                <!-- AQI Level Info -->
                {f'''
                <div style="margin-top: 25px; padding: 20px; background-color: #e8f5e8; border-left: 4px solid #4CAF50; border-radius: 6px;">
                    <h3 style="margin: 0 0 10px 0; color: #2e7d32; font-size: 18px;">📊 ระดับคุณภาพอากาศ</h3>
                    <p style="margin: 0; color: #333333; font-size: 14px; line-height: 1.5;">
                        <strong>0-50:</strong> ดี (เขียว) | <strong>51-100:</strong> ปานกลาง (เหลือง) | 
                        <strong>101-150:</strong> มีผลกระทบ (ส้ม) | <strong>151-200:</strong> ไม่ดี (แดง) | 
                        <strong>201+:</strong> อันตราย (ม่วง)
                    </p>
                </div>
                ''' if avg_data.get('AQI') is not None else ''}
                
                <!-- Footer -->
                <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e0e0; text-align: center;">
                    <p style="color: #666666; font-size: 14px; margin: 0;">
                        💌 ขอบคุณที่ใช้บริการแจ้งเตือนคุณภาพอากาศ ECP Air Quality
                    </p>
                </div>
            </div>
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
        print(f"Daily air quality email sent to {email} ({location})")
        return True
    except Exception as e:
        print(f"Error sending daily air quality email: {e}")
        return False