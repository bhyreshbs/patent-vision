"""Synthetic 'product photos' with exact ground-truth masks, used as reviewed references.

Each generator returns (image_bgr, truth_mask) where truth_mask is the complete product silhouette.
Photos get soft shadows, noise and slight blur so they behave like real images.
"""
import cv2
import numpy as np

LIGHT_BG = (236, 238, 238)
DARK_BG = (28, 28, 30)


class Canvas:
    def __init__(self, w: int, h: int, bg: tuple[int, int, int], seed: int = 0):
        self.w, self.h, self.rng = w, h, np.random.default_rng(seed)
        self.img = np.full((h, w, 3), bg, np.uint8)
        # gentle vignette so the background is not perfectly flat
        yy, xx = np.mgrid[0:h, 0:w]
        v = 1.0 - 0.06 * (((xx - w / 2) / w) ** 2 + ((yy - h / 2) / h) ** 2) * 4
        self.img = np.clip(self.img * v[:, :, None], 0, 255).astype(np.uint8)
        self.truth = np.zeros((h, w), np.uint8)

    def shape(self, color, fn) -> None:
        """Draw the same shape on the photo (colour) and on the truth mask (255)."""
        fn(self.img, color)
        fn(self.truth, 255)

    def shadow(self, cx: int, cy: int, rx: int, ry: int, strength: float = 0.22) -> None:
        layer = np.zeros((self.h, self.w), np.float32)
        cv2.ellipse(layer, (cx, cy), (rx, ry), 0, 0, 360, 1.0, -1)
        layer = cv2.GaussianBlur(layer, (0, 0), 14)
        self.img = (self.img * (1 - strength * layer[:, :, None])).astype(np.uint8)

    def finish(self, noise: float = 3.0) -> tuple[np.ndarray, np.ndarray]:
        img = cv2.GaussianBlur(self.img, (0, 0), 1.0).astype(np.float32)
        img += self.rng.normal(0, noise, img.shape)
        return np.clip(img, 0, 255).astype(np.uint8), self.truth


def _rect(x0, y0, x1, y1):
    return lambda im, c: cv2.rectangle(im, (x0, y0), (x1, y1), c, -1)


def _rrect(x0, y0, x1, y1, r):
    def draw(im, c):
        cv2.rectangle(im, (x0 + r, y0), (x1 - r, y1), c, -1)
        cv2.rectangle(im, (x0, y0 + r), (x1, y1 - r), c, -1)
        for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)):
            cv2.circle(im, (cx, cy), r, c, -1)

    return draw


def cup_with_handle(bg=LIGHT_BG, seed=1, w=900, h=700):
    c = Canvas(w, h, bg, seed)
    c.shadow(400, 600, 230, 40)
    body = np.array([[250, 140], [550, 140], [510, 580], [290, 580]], np.int32)
    c.shape((190, 90, 40), lambda im, col: cv2.fillPoly(im, [body], col))
    c.shape((190, 90, 40), lambda im, col: cv2.ellipse(im, (400, 580), (110, 22), 0, 0, 360, col, -1))
    # both handle ends sit inside the body, so the handle encloses a real see-through opening
    c.shape((190, 90, 40), lambda im, col: cv2.ellipse(im, (500, 330), (140, 120), 0, -90, 90, col, 36))
    cv2.putText(c.img, "ACME", (320, 380), cv2.FONT_HERSHEY_DUPLEX, 2.0, (250, 250, 250), 5, cv2.LINE_AA)
    return c.finish()


def organizer(bg=DARK_BG, seed=2, w=1000, h=650):
    """Two end compartments + middle connector, a cylindrical holder and visible feet."""
    c = Canvas(w, h, bg, seed)
    wood = (150, 195, 225)
    c.shape(wood, _rrect(110, 230, 410, 450, 22))  # left compartment
    c.shape(wood, _rrect(590, 230, 890, 450, 22))  # right compartment
    c.shape(wood, _rect(400, 310, 600, 360))  # middle connector
    c.shape(wood, _rect(470, 110, 530, 320))  # cylindrical holder
    c.shape(wood, lambda im, col: cv2.ellipse(im, (500, 110), (30, 12), 0, 0, 360, col, -1))
    for x in (140, 360, 620, 840):  # feet
        c.shape(wood, _rect(x, 450, x + 36, 482))
    for x0 in (130, 610):  # darker inner compartment wells (no effect on the silhouette)
        cv2.rectangle(c.img, (x0 + 20, 250), (x0 + 260, 400), (95, 140, 170), -1)
    cv2.putText(c.img, "PEN", (180, 340), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (20, 20, 20), 4, cv2.LINE_AA)
    return c.finish()


def thin_spoon(bg=LIGHT_BG, seed=3, w=900, h=600):
    c = Canvas(w, h, bg, seed)
    c.shadow(450, 360, 380, 26, 0.18)
    c.shape((60, 70, 200), lambda im, col: cv2.ellipse(im, (230, 300), (110, 80), 0, 0, 360, col, -1))
    c.shape((60, 70, 200), lambda im, col: cv2.line(im, (320, 300), (760, 300), col, 10, cv2.LINE_AA))
    c.shape((60, 70, 200), lambda im, col: cv2.circle(im, (780, 300), 22, col, -1))
    return c.finish()


def logo_box(bg=(225, 232, 238), seed=4, w=900, h=700):
    """Dark product carrying light text and a small badge: no marks may leak into the outline."""
    c = Canvas(w, h, bg, seed)
    c.shadow(450, 600, 260, 34)
    c.shape((70, 40, 20), _rrect(200, 170, 700, 570, 40))
    cv2.putText(c.img, "LOGO 123", (250, 380), cv2.FONT_HERSHEY_DUPLEX, 2.0, (245, 245, 245), 6, cv2.LINE_AA)
    cv2.circle(c.img, (620, 240), 26, (240, 240, 240), -1)
    return c.finish()


def single_compartment_only(organizer_truth: np.ndarray) -> np.ndarray:
    """A 'wrong component' mask: only the left compartment of the organizer."""
    m = np.zeros_like(organizer_truth)
    m[:, :420] = organizer_truth[:, :420]
    return m


def encode(img: np.ndarray, ext: str = ".png") -> bytes:
    ok, buf = cv2.imencode(ext, img)
    assert ok
    return buf.tobytes()
