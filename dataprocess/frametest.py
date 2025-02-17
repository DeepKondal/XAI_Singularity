import cv2

def get_video_frame_count(video_path):
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return total_frames

video_path = "dataprocess/test_video/__lt03EF4ao.mp4"  # Change to your video path
frame_count = get_video_frame_count(video_path)
print(f"Total Frames in Video: {frame_count}")
