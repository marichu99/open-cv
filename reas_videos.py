import cv2 as cv


def resizeFrame(frame, scale=0.75):
    width = int(frame.shape[1] * scale)
    height = int(frame.shape[0] * scale)
    
    dimensions = (width, height)
    return cv.resize(frame, dimensions, interpolation=cv.INTER_AREA)


def changeRes(width, height):
    
    # only works for live video, not for pre-recorded videos
    capture.set(3, width)
    capture.set(4, height)

capture = cv.VideoCapture('Videos/dog.mp4')

# read frame by frame
while True:
    isTrue, frame = capture.read()
    
    if isTrue:
        frame = resizeFrame(frame, scale=0.2)  # Resize each frame to 20% of its original size
        cv.imshow('Video',frame)
        
        if cv.waitKey(20) & 0xFF == ord('d'):
            break
    else:
        break
    
capture.release()
cv.destroyAllWindows()