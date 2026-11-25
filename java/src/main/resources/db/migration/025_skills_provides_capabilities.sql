-- 025 技能包声明提供的业务技能。
ALTER TABLE skills_packages ADD COLUMN provides_capabilities TEXT NOT NULL DEFAULT '[]';
