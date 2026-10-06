Graji Solutions

About us

Graji is a time-tracking system built for mid to large companies. 
It helps teams manage clock-ins, workdays, breaks, and shift schedules - 
and everything stays on the company’s own machines. No data leaves the local network.

There are two main sides to the system:

- Employees can clock in and out, start and end breaks, check their daily balance, and see their schedules.
- HR / Management get a corporate dashboard to track attendance, manage employees, and keep an eye on the team.


What it does

Graji covers the core features most companies need to track working hours:

- Digital check-in - Clock in, take breaks, and clock out in just a few clicks.
- Daily summary - Quickly see hours worked, expected hours, and the current balance.
- Time-tracking history - Keep a clear record of past workdays for every employee.
- Shifts and schedules - Create and assign shifts without the usual spreadsheet chaos.
- Corporate dashboard - View absences, headcount by department, and basic performance info.
- Employee management - Register new people and keep their details organized.
- Access management - Different permission levels depending on the user’s role.

We kept the interface intentionally simple. The goal is that anyone can get to what they need in three steps or less:

- Access → Check-in → Dashboard


Repository Layout


|-- app.py              Entry point. Creates the app and registers the routes.
|-- requirements.txt    Python dependencies.
|-- README.md           Project documentation.
|-- .gitignore          Files Git should ignore (venv, local database, caches…).
|
|-- db/                 Database and everything related to data.
|-- helpers/            Small reusable utility functions.
|-- static/             CSS, JavaScript, images, and other front-end assets.
|-- templates/          HTML pages rendered by the server.


app.py

This is where everything starts. Configuration, routes and the server itself live here. 
If you want to take a look in the project, this is a good place to start.


db/

Everything related to the database: connection, schema, and the operations that handle employees, time tracking, and schedules. 
Since the data is stored locally, this is also the folder you should back up regularly.


helpers/

Reusable functions used across the application -workday and balance calculations, time formatting, 
validation for CPF, phone numbers and ZIP codes, permission checks, and so on.The idea is simple: 
if a piece of logic is useful in more than one place, it belongs here.


static/

Files that go straight to the browser: CSS, JavaScript, images, logos, backgrounds, etc. 
No business logic lives in this folder.


templates/

The HTML pages the application renders. Each main screen has its own template:

- Login
- Employee dashboard
- Clock-in
- Corporate dashboard (HR)
- Employee list
- New employee


Running the Project
-------
-------
-------

Backup

Graji keeps its database locally, backups regular are important.
To backup, copy the contents of the db/ folder somewhere safe - ideally to a different disk - 
so you don’t lose everything if something goes wrong with the original machine.


Roadmap

We’re building Graji in stages:

1. Where we are - Idea validation, UX research, interface design, and the Figma mockup.
   Status: Done

2. Next step - Build the working MVP (front-end, back-end, and database).
   Status: In progress

3. Beta - Test with real users, fix issues, and improve based on feedback.

4. Final delivery - A polished, ready-to-use version of Graji.


Team

- Isaque Gracino Accarini - Scrum Master
- João Pedro Cazarotti Batista
- Guilherme Caetano Poppi Travensolo
- Richard Sasso Silva
- Aquiles Souza Martins
