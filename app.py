import os
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import Config
from models import get_db, init_db
from storage import allowed_file, save_upload

app = Flask(__name__)
app.config.from_object(Config)

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
init_db()

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
)


def cleanup_old_pending():
    db = get_db()
    old = db.execute(
        """
        SELECT id, filename
        FROM images
        WHERE status = 'pending'
          AND uploaded_at < datetime('now', '-7 days')
        """
    ).fetchall()

    for row in old:
        path = os.path.join(app.config["UPLOAD_FOLDER"], row["filename"])
        if os.path.exists(path):
            os.remove(path)
        db.execute("DELETE FROM images WHERE id = ?", (row["id"],))
    db.commit()


def enforce_approved_limit():
    db = get_db()
    approved = db.execute(
        """
        SELECT id, filename
        FROM images
        WHERE status = 'approved'
        ORDER BY approved_at DESC, uploaded_at DESC, id DESC
        """
    ).fetchall()

    max_items = app.config["MAX_APPROVED_IMAGES"]
    if len(approved) <= max_items:
        return

    to_delete = approved[max_items:]
    for row in to_delete:
        path = os.path.join(app.config["UPLOAD_FOLDER"], row["filename"])
        if os.path.exists(path):
            os.remove(path)
        db.execute("DELETE FROM images WHERE id = ?", (row["id"],))
    db.commit()


def get_gallery_items():
    db = get_db()
    images = db.execute(
        """
        SELECT *
        FROM images
        WHERE status IN ('pending', 'approved')
        ORDER BY uploaded_at DESC, id DESC
        """
    ).fetchall()

    images = [dict(row) for row in images]

    approved_ids = [img["id"] for img in images if img["status"] == "approved"]
    fading_count = app.config["FADING_COUNT"]
    fading_ids = set(approved_ids[-fading_count:]) if approved_ids else set()

    for img in images:
        img["fading"] = img["id"] in fading_ids

    return images, len(approved_ids), len(fading_ids)


def require_admin():
    if not session.get("admin"):
        return False
    return True


@app.route("/")
def gallery():
    cleanup_old_pending()
    images, approved_count, fading_count = get_gallery_items()
    return render_template(
        "gallery.html",
        images=images,
        approved_count=approved_count,
        fading_count=fading_count,
        max_approved=app.config["MAX_APPROVED_IMAGES"],
    )


@app.route("/upload", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def upload():
    if request.method == "POST":
        file = request.files.get("image")
        caption = request.form.get("caption", "").strip()

        if not file or not file.filename:
            flash("Choose a file first.", "error")
            return redirect(url_for("upload"))

        if not allowed_file(file.filename):
            flash("Unsupported file type.", "error")
            return redirect(url_for("upload"))

        try:
            filename, media_type = save_upload(file)
        except Exception:
            flash("That upload could not be processed.", "error")
            return redirect(url_for("upload"))

        db = get_db()
        db.execute(
            """
            INSERT INTO images (filename, caption, status, media_type, uploaded_at)
            VALUES (?, ?, 'pending', ?, datetime('now'))
            """,
            (filename, caption, media_type),
        )
        db.commit()
        flash("Uploaded successfully. Awaiting approval.", "success")
        return redirect(url_for("gallery"))

    return render_template("upload.html")

@app.route("/terms")
def terms():
    return render_template("terms.html")

@app.route("/image/<int:image_id>")
def image(image_id):
    db = get_db()
    item = db.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    if not item:
        abort(404)
    return render_template("image.html", image=dict(item))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == app.config["ADMIN_PASSWORD"]:
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect password.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("gallery"))


@app.route("/admin")
def admin_dashboard():
    if not require_admin():
        return redirect(url_for("admin_login"))

    db = get_db()
    pending = db.execute(
        "SELECT * FROM images WHERE status = 'pending' ORDER BY uploaded_at DESC, id DESC"
    ).fetchall()
    approved = db.execute(
        "SELECT * FROM images WHERE status = 'approved' ORDER BY approved_at DESC, uploaded_at DESC, id DESC LIMIT 50"
    ).fetchall()

    return render_template(
        "admin.html",
        pending=[dict(row) for row in pending],
        approved=[dict(row) for row in approved],
    )


@app.route("/admin/approve/<int:image_id>", methods=["POST"])
def approve(image_id):
    if not require_admin():
        return redirect(url_for("admin_login"))

    db = get_db()
    db.execute(
        "UPDATE images SET status = 'approved', approved_at = datetime('now') WHERE id = ?",
        (image_id,),
    )
    db.commit()
    enforce_approved_limit()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reject/<int:image_id>", methods=["POST"])
def reject(image_id):
    if not require_admin():
        return redirect(url_for("admin_login"))

    db = get_db()
    img = db.execute("SELECT filename FROM images WHERE id = ?", (image_id,)).fetchone()
    if img:
        path = os.path.join(app.config["UPLOAD_FOLDER"], img["filename"])
        if os.path.exists(path):
            os.remove(path)
        db.execute("DELETE FROM images WHERE id = ?", (image_id,))
        db.commit()

    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    app.run(debug=True)
