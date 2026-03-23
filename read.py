import cv2 as cv

img = cv.imread('Photos/cat_large.jpg')

# cv.imshow('Cat', img)
cv.imshow('Cat-large', img)

cv.waitKey(0)