"""Streamlit entry point for TennisPose's local single-photo MVP."""

from __future__ import annotations

import cv2
import numpy as np
import streamlit as st

from tennis360.image_input import UploadedImageError, decode_uploaded_image
from tennis360.pose_detector import (
    DEFAULT_MINIMUM_VISIBILITY,
    DEFAULT_TROPHY_MAXIMUM,
    DEFAULT_TROPHY_MINIMUM,
    AnalysisReport,
    ModelFileMissingError,
    analyze_rgb_image,
    get_detector,
)

MAX_DISPLAY_WIDTH = 1000

ARM_CHOICES = {
    "Auto-detect racket arm": "auto",
    "Player's right arm": "right",
    "Player's left arm": "left",
}

st.set_page_config(page_title="TennisPose", page_icon="🎾", layout="wide")


@st.cache_resource(show_spinner=False)
def load_detector() -> object:
    """Load the pose model once per server process rather than once per upload."""

    return get_detector()


def fit_result_image(image_rgb: np.ndarray) -> np.ndarray:
    """Downscale only very large photos so the annotation stays sharp on screen."""

    height, width = image_rgb.shape[:2]
    if width <= MAX_DISPLAY_WIDTH:
        return image_rgb
    scale = MAX_DISPLAY_WIDTH / width
    return cv2.resize(
        image_rgb,
        (MAX_DISPLAY_WIDTH, max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )


def render_verdict(report: AnalysisReport, minimum: float, maximum: float) -> None:
    """Show the headline result: one angle, one colour, one sentence."""

    angle_column, status_column, range_column = st.columns(3)
    angle_column.metric("Estimated elbow angle", f"{report.angle_degrees:.1f}°")
    range_column.metric("Target range", f"{minimum:.0f}°–{maximum:.0f}°")

    if report.in_demo_range:
        status_column.metric("Result", "🟢 Green")
        st.success(f"**Green — in range.** {report.message}")
    else:
        status_column.metric("Result", "🔴 Red")
        st.error(f"**Red — adjust.** {report.message}")

    if report.confidence == "moderate":
        st.warning(
            "Moderate repeat agreement: some readings differ or a pass was rejected. "
            "The angle is an estimate."
        )
    st.caption("Green/red assesses this elbow estimate against your target; it does not grade the entire serve.")


def render_measurement_detail(report: AnalysisReport) -> None:
    """Expose the working behind the number so the result stays checkable."""

    spread = report.spread_degrees or 0.0
    with st.expander("How this number was measured"):
        st.markdown(
            f"""
- **Arm measured:** player's {report.arm} arm
  ({'auto-detected' if report.arm_was_detected else 'selected'})
- **Angle source:** estimated MediaPipe 3D world landmarks (shoulder → elbow → wrist)
- **Valid passes:** {report.sample_count}/{report.attempted_passes} (original, downscaled, mirrored, two small rotations) —
  the reported value is their median
- **Observed readings:** {report.minimum_angle_degrees:.1f}°–{report.maximum_angle_degrees:.1f}° (full spread {spread:.1f}°)
- **Repeat agreement:** {report.confidence}; this is not an accuracy probability or confidence interval
- **Stage check:** preparation cues verified on every accepted pass; manual arm selection also uses this check
"""
        )
        if report.focused_on_player:
            st.caption("One extra pass located the small player before the five measurement passes.")
        if report.projected_angle_degrees is not None:
            st.caption(
                f"For comparison, the flat 2D image-plane angle is "
                f"{report.projected_angle_degrees:.0f}°. It differs whenever the arm "
                "points toward or away from the camera. Pixel aspect ratio is "
                "accounted for. Only estimated 3D landmarks decide the verdict."
            )


def main() -> None:
    st.title("🎾 TennisPose")
    st.caption(
        "Upload one serve photo. TennisPose finds the shoulder, elbow, and wrist, "
        "estimates the racket-arm elbow angle in 3D, and shows green, red, or "
        "cannot-analyze."
    )

    with st.sidebar:
        st.header("Analysis settings")
        arm_label = st.radio("Arm to inspect", options=tuple(ARM_CHOICES))
        arm = ARM_CHOICES[arm_label]
        if arm == "auto":
            st.caption(
                "At the trophy position the tossing arm is straight and high while "
                "the racket arm is bent near shoulder height. Auto-detect uses that "
                "difference; manual selection still requires preparation cues."
            )

        minimum, maximum = st.slider(
            "Target elbow range (degrees)",
            min_value=40,
            max_value=180,
            value=(int(DEFAULT_TROPHY_MINIMUM), int(DEFAULT_TROPHY_MAXIMUM)),
            help="Green when the measured angle falls inside this inclusive band.",
        )

        st.divider()
        st.caption(
            "One uploaded photo is processed in the local Python app. "
            "Application code does not save it or upload it to a cloud service."
        )
        uploaded_file = st.file_uploader(
            "Upload a Trophy Pose photo",
            type=("jpg", "jpeg", "png"),
            help="A clear JPEG or PNG with one person and both arms visible (max 10 MB).",
        )

    if uploaded_file is None:
        st.info(
            "Choose one JPEG or PNG photo from the sidebar to begin. A side-on shot "
            "of the trophy position — racket up, elbow bent, tossing arm extended — "
            "works best."
        )
        with st.expander("What this MVP checks, and what it does not"):
            st.markdown(
                """
**It checks one thing:** the racket-arm elbow angle at the serve trophy
position, measured from a single still photo.

**It refuses rather than guesses** when the arm is hidden, the player is too
small in the frame, the photo is not a trophy position, or repeat measurements
of the same photo do not agree.

**It is not** a full serve analysis, a video tracker, a coach, or a medical or
injury-prevention tool. The target range is configurable demonstration logic,
not a validated coaching or clinical standard.
"""
            )
        return

    try:
        image_rgb = decode_uploaded_image(uploaded_file.getvalue())
    except UploadedImageError as error:
        st.error(str(error))
        st.caption(
            "Choose another JPEG or PNG photo within the 10 MB upload and "
            "20 megapixel decode limits."
        )
        return

    try:
        with st.spinner("Finding pose landmarks locally…"):
            load_detector()
            annotated_image, report = analyze_rgb_image(
                image_rgb,
                arm,
                minimum_visibility=DEFAULT_MINIMUM_VISIBILITY,
                demo_minimum=float(minimum),
                demo_maximum=float(maximum),
            )
    except ModelFileMissingError as error:
        st.error("The local pose model is not installed yet.")
        st.code(str(error), language=None)
        st.caption("Run start.command or start.bat to install and verify the model, then reopen the app.")
        return
    except Exception:  # MediaPipe returns platform-specific runtime errors.
        st.error("The local pose analysis could not finish for this photo.")
        st.caption("Choose a clear JPEG or PNG with one visible person, then try again.")
        return

    display_image = fit_result_image(annotated_image)
    if report.focused_on_player:
        st.caption("A fixed local crop focuses the small player. The displayed image is this crop; cropping does not establish angle accuracy.")
    image_options = {"width": 480} if report.focused_on_player else {"use_container_width": True}

    if report.status == "cannot_analyze":
        st.warning(f"**Cannot analyze.** {report.message}")
        st.caption(
            f"Reason: {report.reason_code}. No score was generated. "
            "Use a clear view of both arms at the preparation checkpoint."
        )
        st.image(display_image, **image_options)
        return

    render_verdict(report, float(minimum), float(maximum))
    st.image(display_image, **image_options)
    render_measurement_detail(report)
    st.caption(
        "The target range is configurable demonstration logic, not a medically or "
        "professionally validated standard."
    )


if __name__ == "__main__":
    main()
