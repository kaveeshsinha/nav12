# NaV12

NaV12 is a Flask-based web application themed around high-performance cars.

The application includes user signup, login authentication, and a car-themed dashboard. User account data is stored in an Excel workbook using Python's `openpyxl` library.

## Features

- User registration
- Duplicate username validation
- User login authentication
- "User not found" handling
- "Incorrect credentials" handling
- Car-themed dashboard
- Dark automotive UI
- Excel-based user storage
- Flask backend
- Production deployment support

## Tech Stack

- Python
- Flask
- HTML5
- CSS3
- OpenPyXL
- Gunicorn
- Excel (`users.xlsx`)

## Project Structure

```text
NaV12/
├── app.py
├── requirements.txt
├── README.md
├── wsgi_pythonanywhere.py
├── data/
│   └── users.xlsx
└── templates/
    ├── auth.html
    ├── base.html
    ├── dashboard.html
    ├── error.html
    ├── login.html
    ├── signup.html
    └── styles.html
