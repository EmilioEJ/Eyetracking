import cv2
import mediapipe as mp
import pygame
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.pipeline import make_pipeline
from collections import deque
import sys
import os
from datetime import datetime

# --- Setup MediaPipe ---
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
    refine_landmarks=True
)

# --- Setup PyGame ---
pygame.init()
info = pygame.display.Info()
screen_width, screen_height = info.current_w, info.current_h
screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)
pygame.display.set_caption("Advanced Eye-Tracking Calibration & Prediction")

# --- Colors ---
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED   = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE  = (0, 120, 255)
GRAY  = (100, 100, 100)

# --- Calibration Points ---
margin = 100
calibration_points = [
    (margin, margin),
    (screen_width // 2, margin),
    (screen_width - margin, margin),
    (margin, screen_height // 2),
    (screen_width // 2, screen_height // 2),
    (screen_width - margin, screen_height // 2),
    (margin, screen_height - margin),
    (screen_width // 2, screen_height - margin),
    (screen_width - margin, screen_height - margin)
]

# --- State Variables ---
STATE_WELCOME = 0
STATE_CALIBRATING = 1
STATE_TRACKING = 2

current_state = STATE_WELCOME
current_calibration_point = 0
calibration_data = []

# Using PolynomialFeatures (degree=2) for non-linear mapping
model = make_pipeline(PolynomialFeatures(degree=2), LinearRegression())

# --- Tracking / Heatmap Variables ---
position_buffer = deque(maxlen=10)
heatmap = np.zeros((screen_height, screen_width), dtype=np.float32)
stable_threshold = 20
stable_increment = 10.0
base_increment   = 2.0
circle_radius = 40
last_heatmap_pos = None

fixation_data = {}
prev_time = pygame.time.get_ticks()

# --- Calibration Timer & Buffer ---
calibration_duration = 3000 # ms
calibration_start_time = None
calibration_gaze_buffer = []

def get_gaze_point(facial_landmarks):
    try:
        right_idx = [469, 470, 471, 472]
        left_idx = [474, 475, 476, 477]
        right_pts = [facial_landmarks.landmark[i] for i in right_idx]
        left_pts = [facial_landmarks.landmark[i] for i in left_idx]
        right_center = (sum(pt.x for pt in right_pts)/len(right_pts),
                        sum(pt.y for pt in right_pts)/len(right_pts))
        left_center = (sum(pt.x for pt in left_pts)/len(left_pts),
                       sum(pt.y for pt in left_pts)/len(left_pts))
        gaze_x = (right_center[0] + left_center[0]) / 2
        gaze_y = (right_center[1] + left_center[1]) / 2
        return gaze_x, gaze_y
    except Exception:
        return facial_landmarks.landmark[33].x, facial_landmarks.landmark[33].y

def reset_calibration():
    global current_calibration_point, calibration_data, current_state, calibration_start_time, calibration_gaze_buffer, heatmap, fixation_data, position_buffer
    current_calibration_point = 0
    calibration_data = []
    current_state = STATE_CALIBRATING
    calibration_start_time = pygame.time.get_ticks()
    calibration_gaze_buffer = []
    heatmap = np.zeros((screen_height, screen_width), dtype=np.float32)
    fixation_data = {}
    position_buffer.clear()

def draw_welcome_screen():
    screen.fill(BLACK)
    font_title = pygame.font.Font(None, 80)
    font_sub = pygame.font.Font(None, 40)
    
    title = font_title.render("Advanced Eye-Tracking", True, WHITE)
    inst1 = font_sub.render("Instrucciones de calibración:", True, WHITE)
    inst2 = font_sub.render("- Mantén la cabeza quieta y mira fijamente al punto verde.", True, GRAY)
    inst3 = font_sub.render("- El punto verde mostrará un anillo de progreso (3 segundos).", True, GRAY)
    inst4 = font_sub.render("- Una vez completada la calibración, verás tu mapa de calor en tiempo real.", True, GRAY)
    inst5 = font_sub.render("Controles:", True, WHITE)
    inst6 = font_sub.render("[R] Recalibrar  |  [C] Limpiar Mapa  |  [S] Guardar y Salir  |  [ESC] Salir", True, GREEN)
    
    start_text = font_title.render("Presiona ESPACIO para comenzar", True, BLUE)
    
    screen.blit(title, (screen_width//2 - title.get_width()//2, 100))
    screen.blit(inst1, (screen_width//2 - 400, 250))
    screen.blit(inst2, (screen_width//2 - 380, 300))
    screen.blit(inst3, (screen_width//2 - 380, 350))
    screen.blit(inst4, (screen_width//2 - 380, 400))
    screen.blit(inst5, (screen_width//2 - 400, 500))
    screen.blit(inst6, (screen_width//2 - inst6.get_width()//2, 550))
    
    # Pulsing effect for start text
    pulse = (np.sin(pygame.time.get_ticks() / 300.0) + 1) / 2 # 0 to 1
    start_text.set_alpha(int(255 * pulse))
    screen.blit(start_text, (screen_width//2 - start_text.get_width()//2, 700))
    
    pygame.display.flip()

def draw_calibration_screen(point, progress_ratio):
    screen.fill(BLACK)
    # Dibuja los otros puntos
    for i, p in enumerate(calibration_points):
        if i != current_calibration_point:
            pygame.draw.circle(screen, GRAY, p, 10, 1)
            
    # Dibuja el punto actual
    pygame.draw.circle(screen, GREEN, point, 20, 0)
    
    # Arco de progreso (animación de borde)
    rect = pygame.Rect(point[0] - 30, point[1] - 30, 60, 60)
    start_angle = np.pi / 2
    end_angle = start_angle + (progress_ratio * 2 * np.pi)
    if progress_ratio > 0:
        # Pygame draw arc uses radians, start and stop
        # Invert axes behavior for pygame
        pygame.draw.arc(screen, WHITE, rect, start_angle, end_angle, 5)
        
    font = pygame.font.Font(None, 50)
    text = font.render(f"Punto {current_calibration_point+1}/{len(calibration_points)}", True, WHITE)
    screen.blit(text, (screen_width//2 - text.get_width()//2, 50))
    pygame.display.flip()

def train_model():
    global model
    X = np.array([[d["eye_x"], d["eye_y"]] for d in calibration_data])
    y = np.array([[d["screen_x"], d["screen_y"]] for d in calibration_data])
    model.fit(X, y)

def predict_screen_position(gaze_x, gaze_y):
    if current_state == STATE_TRACKING:
        pred = model.predict([[gaze_x, gaze_y]])[0]
        return int(pred[0] * screen_width), int(pred[1] * screen_height)
    return None

def smooth_position(new_pos):
    position_buffer.append(new_pos)
    avg_x = int(np.mean([p[0] for p in position_buffer]))
    avg_y = int(np.mean([p[1] for p in position_buffer]))
    return (avg_x, avg_y)

def save_and_exit():
    # Asegurar que las carpetas existan
    os.makedirs("fixation_data", exist_ok=True)
    os.makedirs("Gaze_Images", exist_ok=True)
    
    # Obtener fecha y hora actual
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    # Save CSV
    if fixation_data:
        fixation_df = pd.DataFrame(list(fixation_data.items()), columns=["Position", "Time_ms"])
        # Format the tuple (x,y) into separate columns
        fixation_df['X'] = fixation_df['Position'].apply(lambda pos: pos[0])
        fixation_df['Y'] = fixation_df['Position'].apply(lambda pos: pos[1])
        fixation_df.drop(columns=['Position'], inplace=True)
        fixation_df = fixation_df[['X', 'Y', 'Time_ms']]
        
        csv_filename = os.path.join("fixation_data", f"fixation_data_{timestamp}.csv")
        fixation_df.to_csv(csv_filename, index=False)
        print(f"Datos de fijación guardados en '{csv_filename}'.")
    
    # Save Heatmap Image
    heatmap_final = np.uint8(np.clip(heatmap, 0, 255))
    heatmap_color_final = cv2.applyColorMap(heatmap_final, cv2.COLORMAP_JET)
    img_filename = os.path.join("Gaze_Images", f"heatmap_{timestamp}.png")
    cv2.imwrite(img_filename, heatmap_color_final)
    print(f"Mapa de calor guardado en '{img_filename}'.")
    
    cap.release()
    pygame.quit()
    sys.exit()

cap = cv2.VideoCapture(0)

running = True
while running:
    current_time = pygame.time.get_ticks()
    delta_time = current_time - prev_time
    prev_time = current_time
    
    ret, frame = cap.read()
    if not ret:
        break

    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb_frame)
    gaze_x, gaze_y = None, None
    
    if results.multi_face_landmarks:
        facial_landmarks = results.multi_face_landmarks[0]
        gaze_x, gaze_y = get_gaze_point(facial_landmarks)

    if current_state == STATE_WELCOME:
        draw_welcome_screen()
        
    elif current_state == STATE_CALIBRATING:
        if calibration_start_time is None:
            calibration_start_time = current_time
        
        elapsed = current_time - calibration_start_time
        progress_ratio = min(elapsed / calibration_duration, 1.0)
        
        target_pt = calibration_points[current_calibration_point]
        draw_calibration_screen(target_pt, progress_ratio)
        
        # Buffer gaze for the last second of the calibration point to stabilize
        if gaze_x is not None and elapsed > (calibration_duration - 1000):
            calibration_gaze_buffer.append((gaze_x, gaze_y))
            
        if elapsed >= calibration_duration:
            # Average the gaze
            if calibration_gaze_buffer:
                avg_gaze_x = np.mean([p[0] for p in calibration_gaze_buffer])
                avg_gaze_y = np.mean([p[1] for p in calibration_gaze_buffer])
            else:
                avg_gaze_x, avg_gaze_y = gaze_x, gaze_y # Fallback
                
            if avg_gaze_x is not None:
                calibration_data.append({
                    "eye_x": avg_gaze_x,
                    "eye_y": avg_gaze_y,
                    "screen_x": target_pt[0] / screen_width,
                    "screen_y": target_pt[1] / screen_height
                })
                current_calibration_point += 1
                calibration_start_time = current_time
                calibration_gaze_buffer = []
                
                if current_calibration_point >= len(calibration_points):
                    train_model()
                    current_state = STATE_TRACKING
            else:
                # No face detected, retry point
                calibration_start_time = current_time

    elif current_state == STATE_TRACKING:
        if gaze_x is not None:
            predicted_pos = predict_screen_position(gaze_x, gaze_y)
            if predicted_pos:
                smoothed_pos = smooth_position(predicted_pos)
                
                # Fixation logic - accumulate delta_time
                fixation_key = tuple(smoothed_pos)
                fixation_data[fixation_key] = fixation_data.get(fixation_key, 0) + delta_time
                
                if last_heatmap_pos is not None:
                    dist = np.linalg.norm(np.array(smoothed_pos) - np.array(last_heatmap_pos))
                    intensity_value = stable_increment if dist < stable_threshold else base_increment
                else:
                    intensity_value = base_increment
                last_heatmap_pos = smoothed_pos
                
                # Acumular intensidad en el heatmap
                mask = np.zeros_like(heatmap)
                cv2.circle(mask, smoothed_pos, circle_radius, intensity_value, thickness=-1)
                heatmap = heatmap + mask
                
                # Visualizar el heatmap
                heatmap_disp = np.uint8(np.clip(heatmap, 0, 255))
                heatmap_color = cv2.applyColorMap(heatmap_disp, cv2.COLORMAP_JET)
                heatmap_color_rgb = cv2.cvtColor(heatmap_color, cv2.COLOR_BGR2RGB)
                
                # Transpose for PyGame (W, H, 3)
                heatmap_surface = pygame.surfarray.make_surface(np.transpose(heatmap_color_rgb, (1, 0, 2)))
                heatmap_surface.set_alpha(150)
                
                screen.fill(BLACK)
                screen.blit(heatmap_surface, (0, 0))
                pygame.draw.circle(screen, RED, smoothed_pos, 60, 5) # red bubble
                
                # UI text
                font = pygame.font.Font(None, 36)
                text = font.render("[R] Recalibrar | [C] Limpiar | [S] Guardar/Salir", True, WHITE)
                screen.blit(text, (10, 10))
                
                pygame.display.flip()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            save_and_exit()
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                save_and_exit()
            elif event.key == pygame.K_SPACE and current_state == STATE_WELCOME:
                reset_calibration()
            elif event.key == pygame.K_r:
                reset_calibration()
            elif event.key == pygame.K_c and current_state == STATE_TRACKING:
                heatmap = np.zeros((screen_height, screen_width), dtype=np.float32)
                fixation_data = {}
            elif event.key == pygame.K_s:
                save_and_exit()
