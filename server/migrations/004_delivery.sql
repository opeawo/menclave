CREATE TABLE job_deliveries(job TEXT NOT NULL REFERENCES jobs(id),recipient TEXT NOT NULL,state TEXT NOT NULL,updated INTEGER NOT NULL,PRIMARY KEY(job,recipient));
