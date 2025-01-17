CREATE TABLE income (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT NOT NULL,
    amount REAL NOT NULL,
    source TEXT NOT NULL,
    date DATE NOT NULL,
    description TEXT,
    FOREIGN KEY (owner) REFERENCES users(username)
);

CREATE TABLE sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    owner TEXT NOT NULL,
    FOREIGN KEY (owner) REFERENCES users(username)
);

