create table collections (
	uid integer primary key autoincrement,
	name text UNIQUE,
	desc text,
	date_created integer,
	date_modified integer
);

create table photos (
	uid integer primary key autoincrement,
	exif blob,
	crc integer,
	hash text,
	micro_thumb blob,
	deleted integer
);

create table files (
	collection_id integer NOT NULL,
	photo_id integer NOT NULL,
	name text NOT NULL,
	path text NOT NULL,
	mtime integer,
	ctime integer,
	FOREIGN KEY(collection_id) REFERENCES uid(collections)
	FOREIGN KEY(photo_id) REFERENCES uid(photos)
);
