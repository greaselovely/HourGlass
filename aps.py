from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

def download_images():
    print(f"Downloading images at {datetime.now()}")

def get_sun_times():
    # Placeholder for your actual logic to fetch sunrise and sunset times
    # For the sake of example, let's assume it returns two datetime objects
    sunrise = datetime.now().replace(hour=6, minute=30)  # 6:30 AM today
    sunset = datetime.now().replace(hour=18, minute=30)  # 6:30 PM today
    return sunrise, sunset

def schedule_tasks():
    scheduler = BackgroundScheduler()

    sunrise, sunset = get_sun_times()

    # Schedule download_images to run every day at sunrise
    scheduler.add_job(download_images, 'cron', hour=sunrise.hour, minute=sunrise.minute)

    # Here, instead of stopping a task at sunset, we schedule another task that could serve as a marker or perform another action
    scheduler.add_job(lambda: print("Sunset reached. Consider stopping or adjusting tasks."),
                      'cron', hour=sunset.hour, minute=sunset.minute)

    scheduler.start()

    # Keep the script running to maintain the scheduler alive
    try:
        # This is a simple way to keep the main thread alive
        while True:
            pass
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

if __name__ == "__main__":
    schedule_tasks()
