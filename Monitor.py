import time
import socket
from datetime import datetime, timedelta
import psutil
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

last_email_time = None
hostname = socket.gethostname()
email_interval = timedelta(minutes=10)
log_file = "/var/log/monitoring_spike.log"
spike_data = {}

def record_spike_time(cpu_usage, memory_usage, disk_usage, top_cpu_processes, top_memory_processes):
    spike_time = datetime.now()
    with open(log_file, "a") as log:
        log.write(f"Spike detected at {spike_time}\n")
        log.write(f"CPU USage: {max(cpu_usage)}%\n")
        log.write(f"Memory Usage: {memory_usage}%\n")
        log.write(f"Disk Usage: {disk_usage}%\n")
        log.write("Top CPU Processes:\n")
        for proc in top_cpu_processes:
            log.write(f"PID: {proc[0]}, Name: {proc[1]}, User: {proc[2]}, CPU: {proc[3]}%\n")
        log.write("Top Memory Processes:\n")
        for proc in top_memory_processes:
            log.write(f"PID: {proc[0]}, Name: {proc[1]}, User: {proc[2]}, Memory: {proc[4]:.2f}%\n")
        log.write("\n")
    
    spike_data['time'] = spike_time
    spike_data['top_cpu_processes'] = top_cpu_processes
    spike_data['top_memory_processes'] = top_memory_processes

def get_top_processes():
    processes = [(p.info['pid'], p.info['name'], p.info['username'], p.info['cpu_percent'], p.info['memory_percent'])
                 for p in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent'])]
    top_cpu_processes = sorted(processes, key=lambda x: x[3], reverse=True)[:5]
    top_memory_processes = sorted(processes, key=lambda x: x[4], reverse=True)[:5]
    return top_cpu_processes, top_memory_processes

def get_user_disk_usage(directory):
    usage = psutil.disk_usage(directory)
    return f"Total: {usage.total / (1024 * 1024 * 1024):.2f} GB, Used: {usage.used / (1024 * 1024 * 1024):.2f} GB, Free: {usage.free / (1024 * 1024 * 1024):.2f} GB"

def get_swap_memory_usage():
    swap = psutil.swap_memory()
    return swap.percent

def send_alert_email(subject, body):
    sender_email = ""
    recipient_email = ""

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = recipient_email

    part = MIMEText(body, 'html')
    msg.attach(part)

    with smtplib.SMTP('mailrelay.advancestores.com') as server:
        server.sendmail(sender_email, recipient_email, msg.as_string())

def check_system_utilization():
    global last_email_time, spike_data
    
    cpu_usage = psutil.cpu_percent(interval=1, percpu=True)
    memory_usage = psutil.virtual_memory().percent
    disk_usage = psutil.disk_usage('/').percent
    swap_usage = get_swap_memory_usage()
    
    if max(cpu_usage) > 95 or memory_usage > 95 or disk_usage > 95 or swap_usage > 95:
        record_spike_time(cpu_usage, memory_usage, disk_usage, *get_top_processes())

        top_cpu_processes, top_memory_processes = get_top_processes()

        user_disk_usage = get_user_disk_usage("/")

        subject = f"{hostname} Server Resource Utilization Alert"
        body = f"""
        <html>
        <head>
            <style>
                table {{
                    width: 100%;
                    border-collapse: collapse;
                }}
                th, td {{
                    padding: 8px;
                    text-align: left;
                    border: 1px solid #ddd;
                }}
                th {{
                    background-color: #f2f2f2;
                }}
                .high-usage {{
                    background-color: #f8d7da;
                    color: #721c24;
                }}
            </style>
        </head>
        <body>
            <h2>System Resource Utilization Alert</h2>
            <p>The following system resources are above 95% utilization:</p>
            <table>
                <tr>
                    <th>Resource</th>
                    <th>Usage</th>
                </tr>
                <tr class="{"high-usage" if max(cpu_usage) > 95 else ""}">
                    <td>CPU Usage</td>
                    <td>{max(cpu_usage)}%</td>
                </tr>
                <tr class="{"high-usage" if memory_usage > 95 else ""}">
                    <td>Memory Usage</td>
                    <td>{memory_usage}%</td>
                </tr>
                <tr class="{"high-usage" if disk_usage > 95 else ""}">
                    <td>Disk Usage</td>
                    <td>{disk_usage}%</td>
                </tr>
                <tr class="{"high-usage" if swap_usage > 95 else ""}">
                    <td>Swap Usage</td>
                    <td>{swap_usage}%</td>
                </tr>
            </table>
            <h3>Top Processes by CPU Usage</h3>
            <table>
                <tr>
                    <th>PID</th>
                    <th>Name</th>
                    <th>User</th>
                    <th>CPU Usage</th>
                </tr>"""
        for proc in top_cpu_processes:
            body += f"""
                <tr>
                    <td>{proc[0]}</td>
                    <td>{proc[1]}</td>
                    <td>{proc[2]}</td>
                    <td>{proc[3]}%</td>
                </tr>"""
        body += """
            </table>
            <h3>Top Processes by Memory Usage</h3>
            <table>
                <tr>
                    <th>PID</th>
                    <th>Name</th>
                    <th>User</th>
                    <th>Memory Usage</th>
                </tr>"""
        for proc in top_memory_processes:
            body += f"""
                <tr>
                    <td>{proc[0]}</td>
                    <td>{proc[1]}</td>
                    <td>{proc[2]}</td>
                    <td>{proc[4]:.2f}%</td>
                </tr>"""
        body += f"""
            </table>
            <h3>User Disk Usage in /</h3>
            <pre>{user_disk_usage}</pre>
        </body>
        </html>
        """

        if last_email_time is None or (datetime.now() - last_email_time) >= email_interval:
            send_alert_email(subject, body)
            last_email_time = datetime.now()

    elif last_email_time is not None:
        top_cpu_processes, top_memory_processes = spike_data.get('top_cpu_processes', []), spike_data.get('top_memory_processes', [])
        spike_time = spike_data.get('time', datetime.now())
        normalization_subject = f"{hostname} Server Resource Utilization Comming Back to Normal"
        normalization_body = f"""
        <html>
        <head>
            <style>
                table {{
                    width: 100%;
                    border-collapse: collapse;
                }}
                th, td {{
                    padding: 8px;
                    text-align: left;
                    border: 1px solid #ddd;
                }}
                th {{
                    background-color: #f2f2f2;
                }}
            </style>
        </head>
        <body>
            <h2>Resource Utilization Back to Normal</h2>
            <p>Resource utilization is back to normal.</p>
            <p>Details of the previous spike:</p>
            <p>Spike detected at: {spike_time}</p>
            <h3>Top Processes by CPU Usage During Spike</h3>
            <table>
                <tr>
                    <th>PID</th>
                    <th>Name</th>
                    <th>User</th>
                    <th>CPU Usage</th>
                </tr>"""
        for proc in top_cpu_processes:
            normalization_body += f"""
                <tr>
                    <td>{proc[0]}</td>
                    <td>{proc[1]}</td>
                    <td>{proc[2]}</td>
                    <td>{proc[3]}%</td>
                </tr>"""
        normalization_body += """
            </table>
            <h3>Top Processes by Memory Usage During Spike</h3>
            <table>
                <tr>
                    <th>PID</th>
                    <th>Name</th>
                    <th>User</th>
                    <th>Memory Usage</th>
                </tr>"""
        for proc in top_memory_processes:
            normalization_body += f"""
                <tr>
                    <td>{proc[0]}</td>
                    <td>{proc[1]}</td>
                    <td>{proc[2]}</td>
                    <td>{proc[4]:.2f}%</td>
                </tr>"""
        normalization_body += """
            </table>
        </body>
        </html>
        """
        send_alert_email(normalization_subject, normalization_body)
        last_email_time = None

def main():
    while True:
        check_system_utilization()
        time.sleep(900)  

if __name__ == "__main__":
    main()

