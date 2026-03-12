import os

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash
)
from dotenv import load_dotenv

from config import Config
from models import init_db, get_db
from storage import allowed_file, prepare_upload
from r2_storage import upload_fileobj_to_r2, delete_from_r2

load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)

init_db()


def enforce_approved_limit():
    db = get_db()

    approved = db.execute(
        """
        SELECT id, filename, storage_key
        FROM images
        WHERE status = 'approved'
        ORDER BY uploaded_at DESC, id DESC
        """
    ).fetchall()

    max_items = app.config["MAX_APPROVED_IMAGES"]

    if len(approved) <= max_items:
        return

    to_delete = approved[max_items:]

    for row in to_delete:
        if row["storage_key"]:
            delete_from_r2(row["storage_key"])
        else:
            path = os.path.join(app.config["UPLOAD_FOLDER"], row["filename"])
            if os.path.exists(path):
                os.remove(path)

        db.execute("DELETE FROM images WHERE id = ?", (row["id"],))

    db.commit()


def cleanup_old_pending():
    db = get_db()

    old = db.execute(
        """
        SELECT id, filename, storage_key
        FROM images
        WHERE status = 'pending'
        AND uploaded_at < datetime('now', '-7 days')
        """
    ).fetchall()

    for row in old:
        if row["storage_key"]:
            delete_from_r2(row["storage_key"])
        else:
            path = os.path.join(app.config["UPLOAD_FOLDER"], row["filename"])
            if os.path.exists(path):
                os.remove(path)

        db.execute("DELETE FROM images WHERE id = ?", (row["id"],))

    db.commit()


@app.route("/")
def gallery():
    cleanup_old_pending()

    db = get_db()
    images = db.execute(
        """
        SELECT * FROM images
        WHERE status = 'approved'
        ORDER BY uploaded_at DESC
        LIMIT ?
        """,
        (app.config["MAX_APPROVED_IMAGES"],)
    ).fetchall()

    images = list(images)
    fade_start = max(len(images) - 5, 0)

    for i, img in enumerate(images):
        img = dict(img)
        img["fading"] = i >= fade_start
        images[i] = img

    return render_template("gallery.html", images=images)


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files.get("image")
        caption = request.form.get("caption", "").strip()

        if not file or not file.filename:
            flash("Please choose a file.", "error")
            return redirect(url_for("upload"))

        if not allowed_file(file.filename):
            flash("Unsupported file type.", "error")
            return redirect(url_for("upload"))

        try:
            prepared_file, media_type = prepare_upload(file)
            storage_key, file_url = upload_fileobj_to_r2(
                prepared_file,
                file.filename,
                file.content_type
            )

            db = get_db()
            db.execute(
                """
                INSERT INTO images
                (filename, file_url, storage_key, caption, status, media_type, uploaded_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (file.filename, file_url, storage_key, caption, "pending", media_type),
            )
            db.commit()

            flash("Uploaded. Marked for approval.", "success")
            return redirect(url_for("gallery"))

        except Exception as e:
            flash(f"Upload failed: {e}", "error")
            return redirect(url_for("upload"))

    return render_template("upload.html")


@app.route("/image/<int:image_id>")
def image(image_id):
    db = get_db()
    image = db.execute(
        "SELECT * FROM images WHERE id = ?",
        (image_id,)
    ).fetchone()

    if not image:
        flash("That item does not exist.", "error")
        return redirect(url_for("gallery"))

    return render_template("image.html", image=image)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password")

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
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    db = get_db()

    pending = db.execute(
        "SELECT * FROM images WHERE status='pending' ORDER BY uploaded_at DESC"
    ).fetchall()

    approved = db.execute(
        "SELECT * FROM images WHERE status='approved' ORDER BY uploaded_at DESC LIMIT 50"
    ).fetchall()

    return render_template("admin.html", pending=pending, approved=approved)


@app.route("/admin/approve/<int:image_id>", methods=["POST"])
def approve(image_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    db = get_db()
    db.execute(
        "UPDATE images SET status='approved' WHERE id = ?",
        (image_id,)
    )
    db.commit()

    enforce_approved_limit()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reject/<int:image_id>", methods=["POST"])
def reject(image_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    db = get_db()

    row = db.execute(
        "SELECT filename, storage_key FROM images WHERE id = ?",
        (image_id,)
    ).fetchone()

    if row:
        if row["storage_key"]:
            delete_from_r2(row["storage_key"])
        else:
            path = os.path.join(app.config["UPLOAD_FOLDER"], row["filename"])
            if os.path.exists(path):
                os.remove(path)

    db.execute("DELETE FROM images WHERE id = ?", (image_id,))
    db.commit()

    return redirect(url_for("admin_dashboard"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


if __name__ == "__main__":
    app.run(debug=True)