import cv2
import requests
import argparse
import time

def main():
    parser = argparse.ArgumentParser(description="Samatma Network Camera Streaming Node")
    parser.add_argument("--url", default="http://100.67.122.47:5000", help="Base URL of the Dashboard (e.g. your Tailscale Pi IP)")
    parser.add_argument("--cam", default="node_01", help="A unique string ID you wish to label this camera as")
    parser.add_argument("--device", type=int, default=0, help="Webcam device index (0 is usually default)")
    args = parser.parse_args()
    
    print(f"[*] Attaching to Camera device {args.device}...")
    cap = cv2.VideoCapture(args.device)
    
    if not cap.isOpened():
        print("[!] Fatal: Could not capture from webcam.")
        return

    # Scale down raw resolution to vastly minimize streaming network lag
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    
    print(f"[*] Beginning network stream to: {args.url}/api/upload/{args.cam}")
    print("[*] Press 'q' multiple times to kill the client.")

    consecutive_fails = 0

    while True:
        ret, frame = cap.read()
        if not ret: 
            print("[!] Unable to read frame.")
            break
            
        # Flip frame horizontally to act as a mirror visually
        frame = cv2.flip(frame, 1)

        # Compress to JPEG aggressively for remote latency minimization
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 65]
        result, encoded = cv2.imencode('.jpg', frame, encode_param)
        
        if not result:
            continue

        endpoint = f"{args.url}/api/upload/{args.cam}"
        
        try:
            # Sync POST: Will dynamically cap the FPS stream rate to the network latency natively!
            resp = requests.post(endpoint, files={"frame": encoded.tobytes()}, timeout=2)
            if resp.status_code == 200:
                consecutive_fails = 0
        except requests.exceptions.RequestException as e:
            consecutive_fails += 1
            if consecutive_fails % 30 == 0:
                print(f"[!] Warning: Cannot reach Dashboard Pi Server ({consecutive_fails} failed attempts). Ensure it is running.")
             
        # Present the outbound unannotated viewer for monitoring 
        cv2.imshow("Outbound Stream Manager (Node)", frame)
        if cv2.waitKey(1) == ord('q'): 
            print("[*] Exit signal captured. Terminating node link.")
            break
            
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
