import os
import datetime
import matplotlib.pyplot as plt
from datetime import datetime

def create_time_difference_graph(input_dir, output_dir):
    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Get all jpg files in the input directory
    try:
        files = [f for f in os.listdir(input_dir) if f.endswith('.jpg')]
    except OSError as e:
        print(f"Error accessing directory {input_dir}: {e}")
        return

    if not files:
        print(f"No jpg files found in {input_dir}")
        return

    # Sort files by name (which will sort them chronologically)
    files.sort()

    # Extract timestamps and calculate time differences
    timestamps = []
    time_diffs = []

    for file in files:
        # Extract date and time from filename
        parts = file.split('.')
        if len(parts) < 4:
            print(f"Skipping file with unexpected format: {file}")
            continue
        date_str, time_str = parts[1], parts[2]
        
        # Parse the datetime
        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%m%d%Y %H%M%S")
            timestamps.append(dt)
        except ValueError as e:
            print(f"Error parsing datetime for file {file}: {e}")

    # Calculate time differences
    for i in range(1, len(timestamps)):
        diff = (timestamps[i] - timestamps[i-1]).total_seconds()
        time_diffs.append(diff)

    if not time_diffs:
        print("Not enough valid timestamps to create a graph")
        return

    # Create the graph
    plt.figure(figsize=(16, 9))  # Larger figure size
    plt.plot(range(1, len(time_diffs) + 1), time_diffs, marker='o')
    plt.title('Time Difference Between Consecutive Images')
    plt.xlabel('Image Pair')
    plt.ylabel('Time Difference (seconds)')
    plt.grid(True)
    plt.tight_layout()

    # Generate filename with today's date
    today_date = datetime.now().strftime("%m%d%Y")
    output_filename = f"graph.{today_date}.jpg"
    output_file = os.path.join(output_dir, output_filename)

    # Save the graph as a large jpg in the output directory
    plt.savefig(output_file, format='jpg', dpi=300)
    plt.close()  # Close the plot to free up memory

    print(f"[i]\tGraph saved as {output_file}")
