-- ============================================================
-- ITEM BASE TEMPLATES: 316 базовых строк (base_grade=0)
-- Weapons 130 (12×10 + сферы 10) + бонусы раса/класса по категориям
-- Armors 84, Accessories 78 + расовые/классовые варианты
-- required_race / required_class: id из WaifuRace / WaifuClass (1–7), NULL = нет требования
-- ============================================================

BEGIN;

-- Create item_base_templates table if not exists
CREATE TABLE IF NOT EXISTS item_base_templates (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(128) NOT NULL,
    item_type       VARCHAR(32)  NOT NULL,  -- weapon / armor / ring / amulet
    subtype         VARCHAR(32)  NOT NULL,  -- one_hand/two_hand/offhand/bow/staff/light/medium/heavy/robe/ring/amulet
    attack_type     VARCHAR(16),            -- melee / ranged / magic (NULL for non-weapons)
    tier            INT NOT NULL,           -- 1-10
    level_min       INT NOT NULL,
    level_max       INT NOT NULL,
    dmg_min         INT NOT NULL DEFAULT 0,
    dmg_max         INT NOT NULL DEFAULT 0,
    attack_speed    INT NOT NULL DEFAULT 0, -- min symbols per message
    armor_base      INT NOT NULL DEFAULT 0, -- flat armor (for armor/shields)
    stat1_type      VARCHAR(8),             -- STR/DEX/INT/VIT/CHA/LUK
    stat1_value     INT NOT NULL DEFAULT 0,
    stat2_type      VARCHAR(8),
    stat2_value     INT NOT NULL DEFAULT 0,
    base_price      INT NOT NULL DEFAULT 10,
    sell_price      INT GENERATED ALWAYS AS (GREATEST(1, base_price / 4)) STORED,
    boss_allowed    BOOLEAN NOT NULL DEFAULT TRUE,
    weight          INT NOT NULL DEFAULT 100  -- drop weight
);


-- ── WEAPONS ──────────────────────────────────────────────────
INSERT INTO item_base_templates
  (name, item_type, subtype, attack_type, tier, level_min, level_max,
   dmg_min, dmg_max, attack_speed, armor_base, stat1_type, stat1_value, base_price)
VALUES
  ('Кинжал','weapon','one_hand','melee',1,1,5,3,5,3,0,'DEX',1,8),
  ('Нож охотника','weapon','one_hand','melee',2,6,10,4,7,3,0,'DEX',1,18),
  ('Вакидзаши','weapon','one_hand','melee',3,11,15,5,9,3,0,'DEX',2,35),
  ('Короткий клинок','weapon','one_hand','melee',4,16,20,7,11,3,0,'DEX',2,60),
  ('Гладиус','weapon','one_hand','melee',5,21,25,9,14,3,0,'DEX',2,95),
  ('Ятаган','weapon','one_hand','melee',6,26,30,11,17,3,0,'DEX',3,140),
  ('Фальшион','weapon','one_hand','melee',7,31,35,14,21,3,0,'DEX',3,200),
  ('Кортик','weapon','one_hand','melee',8,36,40,17,26,3,0,'DEX',3,270),
  ('Мистерикл','weapon','one_hand','melee',9,41,45,21,32,3,0,'DEX',4,360),
  ('Теневое жало','weapon','one_hand','melee',10,46,50,26,39,3,0,'DEX',4,460),
  ('Меч','weapon','one_hand','melee',1,1,5,5,8,5,0,'STR',1,10),
  ('Арминг-сворд','weapon','one_hand','melee',2,6,10,7,11,5,0,'STR',1,22),
  ('Длинный меч','weapon','one_hand','melee',3,11,15,9,14,5,0,'STR',2,42),
  ('Бастард-сворд','weapon','one_hand','melee',4,16,20,12,18,5,0,'STR',2,70),
  ('Катана','weapon','one_hand','melee',5,21,25,15,23,5,0,'STR',2,110),
  ('Палаш','weapon','one_hand','melee',6,26,30,19,28,5,0,'STR',3,160),
  ('Клеймор','weapon','two_hand','melee',7,31,35,24,36,5,0,'STR',3,230),
  ('Волчья сталь','weapon','two_hand','melee',8,36,40,30,44,5,0,'STR',4,310),
  ('Рунный меч','weapon','two_hand','melee',9,41,45,37,55,5,0,'STR',4,410),
  ('Экскалибур','weapon','two_hand','melee',10,46,50,46,68,5,0,'STR',5,530),
  ('Ручной топор','weapon','one_hand','melee',1,1,5,6,10,6,0,'STR',1,12),
  ('Боевой топор','weapon','one_hand','melee',2,6,10,8,13,6,0,'STR',1,25),
  ('Секира','weapon','two_hand','melee',3,11,15,11,18,6,0,'STR',2,48),
  ('Бродакс','weapon','two_hand','melee',4,16,20,15,23,6,0,'STR',2,80),
  ('Боевая секира','weapon','two_hand','melee',5,21,25,19,29,6,0,'STR',2,120),
  ('Варварский топор','weapon','two_hand','melee',6,26,30,24,36,6,0,'STR',3,175),
  ('Великий топор','weapon','two_hand','melee',7,31,35,30,45,6,0,'STR',3,250),
  ('Рунный топор','weapon','two_hand','melee',8,36,40,37,56,6,0,'STR',4,340),
  ('Призывной топор','weapon','two_hand','melee',9,41,45,46,69,6,0,'STR',4,450),
  ('Топор бури','weapon','two_hand','melee',10,46,50,57,85,6,0,'STR',5,580),
  ('Короткий лук','weapon','bow','ranged',1,1,5,4,7,4,0,'DEX',1,9),
  ('Длинный лук','weapon','bow','ranged',2,6,10,6,10,4,0,'DEX',1,20),
  ('Охотничий лук','weapon','bow','ranged',3,11,15,8,13,4,0,'DEX',2,38),
  ('Составной лук','weapon','bow','ranged',4,16,20,10,16,4,0,'DEX',2,65),
  ('Военный лук','weapon','bow','ranged',5,21,25,13,20,4,0,'DEX',2,100),
  ('Рекурсивный лук','weapon','bow','ranged',6,26,30,16,25,4,0,'DEX',3,148),
  ('Эльфийский лук','weapon','bow','ranged',7,31,35,20,31,4,0,'DEX',3,210),
  ('Длань леса','weapon','bow','ranged',8,36,40,25,38,4,0,'DEX',3,285),
  ('Серебряная дуга','weapon','bow','ranged',9,41,45,31,47,4,0,'DEX',4,380),
  ('Звёздный лук','weapon','bow','ranged',10,46,50,38,58,4,0,'DEX',4,490),
  ('Посох','weapon','staff','magic',1,1,5,3,6,7,0,'INT',1,10),
  ('Ореховый посох','weapon','staff','magic',2,6,10,4,8,7,0,'INT',1,22),
  ('Боевой посох','weapon','staff','magic',3,11,15,6,11,7,0,'INT',2,42),
  ('Жезл силы','weapon','staff','magic',4,16,20,8,14,7,0,'INT',2,70),
  ('Посох тайн','weapon','staff','magic',5,21,25,10,18,7,0,'INT',2,108),
  ('Лунный посох','weapon','staff','magic',6,26,30,13,22,7,0,'INT',3,158),
  ('Архимагов посох','weapon','staff','magic',7,31,35,16,28,7,0,'INT',3,225),
  ('Посох звёзд','weapon','staff','magic',8,36,40,20,35,7,0,'INT',4,305),
  ('Скипетр бездны','weapon','staff','magic',9,41,45,25,43,7,0,'INT',4,405),
  ('Посох Творения','weapon','staff','magic',10,46,50,31,53,7,0,'INT',5,525),
  ('Деревянный щит','weapon','offhand','melee',1,1,5,0,0,10,4,'VIT',1,7),
  ('Кожаный щит','weapon','offhand','melee',2,6,10,0,0,10,7,'VIT',1,16),
  ('Круглый щит','weapon','offhand','melee',3,11,15,0,0,10,11,'VIT',2,30),
  ('Боевой щит','weapon','offhand','melee',4,16,20,0,0,10,16,'VIT',2,52),
  ('Рыцарский щит','weapon','offhand','melee',5,21,25,0,0,10,22,'VIT',2,80),
  ('Башенный щит','weapon','offhand','melee',6,26,30,0,0,10,29,'VIT',3,118),
  ('Эгида','weapon','offhand','melee',7,31,35,0,0,10,38,'VIT',3,168),
  ('Щит хранителя','weapon','offhand','melee',8,36,40,0,0,10,48,'VIT',4,230),
  ('Зеркальный щит','weapon','offhand','melee',9,41,45,0,0,10,60,'VIT',4,305),
  ('Несокрушимый','weapon','offhand','melee',10,46,50,0,0,10,74,'VIT',5,395);

-- ── WEAPONS (доп. 6 линеек ×10 = 60) ─────────────────────────
INSERT INTO item_base_templates
  (name, item_type, subtype, attack_type, tier, level_min, level_max,
   dmg_min, dmg_max, attack_speed, armor_base, stat1_type, stat1_value, base_price)
VALUES
  ('Жезл искр','weapon','one_hand','magic',1,1,5,3,5,5,0,'INT',1,9),
  ('Угольный жезл','weapon','one_hand','magic',2,6,10,4,7,5,0,'INT',1,20),
  ('Жезл молнии','weapon','one_hand','magic',3,11,15,5,10,5,0,'INT',2,38),
  ('Жезл пронзания','weapon','one_hand','magic',4,16,20,7,12,5,0,'INT',2,64),
  ('Жезл власти','weapon','one_hand','magic',5,21,25,9,15,5,0,'INT',2,100),
  ('Жезл пустоты','weapon','one_hand','magic',6,26,30,11,19,5,0,'INT',3,148),
  ('Жезл звёзд','weapon','one_hand','magic',7,31,35,14,24,5,0,'INT',3,212),
  ('Жезл разлома','weapon','one_hand','magic',8,36,40,17,30,5,0,'INT',4,288),
  ('Жезл конца','weapon','one_hand','magic',9,41,45,21,37,5,0,'INT',4,382),
  ('Жезл сотворения','weapon','one_hand','magic',10,46,50,26,46,5,0,'INT',5,495),
  ('Дубина','weapon','one_hand','melee',1,1,5,5,9,6,0,'STR',1,11),
  ('Булава стража','weapon','one_hand','melee',2,6,10,8,12,6,0,'STR',1,24),
  ('Таранная булава','weapon','one_hand','melee',3,11,15,10,16,6,0,'STR',2,46),
  ('Булава карателя','weapon','one_hand','melee',4,16,20,13,20,6,0,'STR',2,76),
  ('Утренняя звезда','weapon','one_hand','melee',5,21,25,16,25,6,0,'STR',2,118),
  ('Булава инквизитора','weapon','one_hand','melee',6,26,30,20,31,6,0,'STR',3,172),
  ('Шипастый шар','weapon','one_hand','melee',7,31,35,25,38,6,0,'STR',3,246),
  ('Булава титанов','weapon','one_hand','melee',8,36,40,31,47,6,0,'STR',4,332),
  ('Булава падших','weapon','one_hand','melee',9,41,45,38,58,6,0,'STR',4,438),
  ('Булава конца времён','weapon','one_hand','melee',10,46,50,47,71,6,0,'STR',5,565),
  ('Короткое копьё','weapon','two_hand','melee',1,1,5,7,11,6,0,'DEX',1,11),
  ('Пика легиона','weapon','two_hand','melee',2,6,10,10,15,6,0,'DEX',1,26),
  ('Копьё охотника','weapon','two_hand','melee',3,11,15,12,19,6,0,'DEX',2,48),
  ('Спинтон','weapon','two_hand','melee',4,16,20,15,24,6,0,'DEX',2,78),
  ('Копьё фаланги','weapon','two_hand','melee',5,21,25,19,30,6,0,'DEX',2,120),
  ('Копьё дракона','weapon','two_hand','melee',6,26,30,23,37,6,0,'DEX',3,176),
  ('Пика грома','weapon','two_hand','melee',7,31,35,28,45,6,0,'DEX',3,252),
  ('Копьё героя','weapon','two_hand','melee',8,36,40,34,54,6,0,'DEX',4,340),
  ('Алебарда стража','weapon','two_hand','melee',9,41,45,41,65,6,0,'DEX',4,448),
  ('Копьё миров','weapon','two_hand','melee',10,46,50,50,78,6,0,'DEX',5,575),
  ('Лёгкий арбалет','weapon','bow','ranged',1,1,5,5,8,5,0,'DEX',1,10),
  ('Арбалет охотника','weapon','bow','ranged',2,6,10,7,11,5,0,'DEX',1,22),
  ('Тяжёлый арбалет','weapon','bow','ranged',3,11,15,9,14,5,0,'DEX',2,42),
  ('Арбалет стрелка','weapon','bow','ranged',4,16,20,11,18,5,0,'DEX',2,70),
  ('Арбалет гарнизона','weapon','bow','ranged',5,21,25,14,22,5,0,'DEX',2,108),
  ('Осадный арбалет','weapon','bow','ranged',6,26,30,18,28,5,0,'DEX',3,160),
  ('Арбалет чародея','weapon','bow','ranged',7,31,35,22,34,5,0,'DEX',3,228),
  ('Серебряный болт','weapon','bow','ranged',8,36,40,27,42,5,0,'DEX',3,308),
  ('Арбалет призрака','weapon','bow','ranged',9,41,45,33,51,5,0,'DEX',4,410),
  ('Арбалет звёзд','weapon','bow','ranged',10,46,50,41,62,5,0,'DEX',4,528),
  ('Скипетр послушника','weapon','one_hand','magic',1,1,5,3,6,6,0,'INT',1,10),
  ('Скипетр аколита','weapon','one_hand','magic',2,6,10,4,9,6,0,'INT',1,22),
  ('Скипетр жреца','weapon','one_hand','magic',3,11,15,6,12,6,0,'INT',2,42),
  ('Скипетр прорицателя','weapon','one_hand','magic',4,16,20,8,15,6,0,'INT',2,70),
  ('Скипетр иерарха','weapon','one_hand','magic',5,21,25,10,19,6,0,'INT',2,108),
  ('Скипетр света','weapon','one_hand','magic',6,26,30,12,23,6,0,'INT',3,158),
  ('Скипетр суда','weapon','one_hand','magic',7,31,35,15,29,6,0,'INT',3,228),
  ('Скипетр культа','weapon','one_hand','magic',8,36,40,19,36,6,0,'INT',4,310),
  ('Скипетр апостола','weapon','one_hand','magic',9,41,45,23,44,6,0,'INT',4,412),
  ('Скипетр верховного','weapon','one_hand','magic',10,46,50,29,54,6,0,'INT',5,535),
  ('Молот кузнеца','weapon','two_hand','melee',1,1,5,7,11,6,0,'STR',1,13),
  ('Боевой молот','weapon','two_hand','melee',2,6,10,9,14,6,0,'STR',1,27),
  ('Молот карателя','weapon','two_hand','melee',3,11,15,12,19,6,0,'STR',2,50),
  ('Молот великана','weapon','two_hand','melee',4,16,20,16,25,6,0,'STR',2,84),
  ('Молот войны','weapon','two_hand','melee',5,21,25,20,31,6,0,'STR',2,128),
  ('Молот бури','weapon','two_hand','melee',6,26,30,25,38,6,0,'STR',3,186),
  ('Молот титана','weapon','two_hand','melee',7,31,35,31,47,6,0,'STR',3,266),
  ('Рунный молот','weapon','two_hand','melee',8,36,40,38,58,6,0,'STR',4,360),
  ('Молот падших богов','weapon','two_hand','melee',9,41,45,47,71,6,0,'STR',4,476),
  ('Молот мирового древа','weapon','two_hand','melee',10,46,50,58,87,6,0,'STR',5,610);

-- ── ARMORS ───────────────────────────────────────────────────
INSERT INTO item_base_templates
  (name, item_type, subtype, attack_type, tier, level_min, level_max,
   armor_base, stat1_type, stat1_value, base_price)
VALUES
  ('Простая одежда','armor','light',NULL,1,1,5,3,'DEX',1,6),
  ('Кожаная броня','armor','light',NULL,2,6,10,6,'DEX',1,15),
  ('Усиленная кожа','armor','light',NULL,3,11,15,10,'DEX',2,28),
  ('Кожаный доспех','armor','light',NULL,4,16,20,15,'DEX',2,48),
  ('Чешуйчатый доспех','armor','light',NULL,5,21,25,21,'DEX',2,75),
  ('Кираса охотника','armor','light',NULL,6,26,30,28,'DEX',3,110),
  ('Драконья кожа','armor','light',NULL,7,31,35,37,'DEX',3,158),
  ('Теневая броня','armor','light',NULL,8,36,40,47,'DEX',4,215),
  ('Плащ Призрака','armor','light',NULL,9,41,45,59,'DEX',4,285),
  ('Доспех ветра','armor','light',NULL,10,46,50,73,'DEX',5,370),
  ('Стёганая броня','armor','medium',NULL,1,1,5,5,'VIT',1,8),
  ('Кольчуга','armor','medium',NULL,2,6,10,10,'VIT',1,18),
  ('Пластинчатая кольч','armor','medium',NULL,3,11,15,16,'VIT',2,35),
  ('Бригантина','armor','medium',NULL,4,16,20,23,'VIT',2,58),
  ('Полудоспех','armor','medium',NULL,5,21,25,31,'VIT',2,90),
  ('Кираса воина','armor','medium',NULL,6,26,30,41,'VIT',3,132),
  ('Рыцарский доспех','armor','medium',NULL,7,31,35,53,'VIT',3,188),
  ('Мифриловая броня','armor','medium',NULL,8,36,40,66,'VIT',4,255),
  ('Доспех чемпиона','armor','medium',NULL,9,41,45,82,'VIT',4,338),
  ('Святая эгида','armor','medium',NULL,10,46,50,100,'VIT',5,438),
  ('Латы','armor','heavy',NULL,1,1,5,8,'VIT',1,10),
  ('Боевые латы','armor','heavy',NULL,2,6,10,15,'VIT',2,22),
  ('Рыцарские латы','armor','heavy',NULL,3,11,15,24,'VIT',2,42),
  ('Великие латы','armor','heavy',NULL,4,16,20,35,'VIT',3,70),
  ('Доспех паладина','armor','heavy',NULL,5,21,25,47,'VIT',3,108),
  ('Адамантовые латы','armor','heavy',NULL,6,26,30,62,'VIT',4,158),
  ('Осадные латы','armor','heavy',NULL,7,31,35,79,'VIT',4,225),
  ('Броня предков','armor','heavy',NULL,8,36,40,99,'VIT',5,305),
  ('Доспех легенды','armor','heavy',NULL,9,41,45,121,'VIT',5,405),
  ('Несокрушимая броня','armor','heavy',NULL,10,46,50,147,'VIT',5,525),
  ('Грубая мантия','armor','robe',NULL,1,1,5,2,'INT',1,7),
  ('Мантия ученика','armor','robe',NULL,2,6,10,4,'INT',1,16),
  ('Одеяние мага','armor','robe',NULL,3,11,15,7,'INT',2,30),
  ('Мантия тайн','armor','robe',NULL,4,16,20,11,'INT',2,50),
  ('Аркановая мантия','armor','robe',NULL,5,21,25,15,'INT',3,78),
  ('Одеяние звёзд','armor','robe',NULL,6,26,30,20,'INT',3,114),
  ('Мантия архимага','armor','robe',NULL,7,31,35,26,'INT',4,163),
  ('Покров бездны','armor','robe',NULL,8,36,40,33,'INT',4,222),
  ('Одеяние пророка','armor','robe',NULL,9,41,45,41,'INT',5,294),
  ('Мантия Творения','armor','robe',NULL,10,46,50,51,'INT',5,382);

-- ── ARMORS (доп. 4 линейки ×10 = 40) ──────────────────────────
INSERT INTO item_base_templates
  (name, item_type, subtype, attack_type, tier, level_min, level_max,
   armor_base, stat1_type, stat1_value, base_price)
VALUES
  ('Плащ путника','armor','cloak',NULL,1,1,5,2,'DEX',1,6),
  ('Плащ следопыта','armor','cloak',NULL,2,6,10,5,'DEX',1,14),
  ('Плащ ветра','armor','cloak',NULL,3,11,15,8,'DEX',2,26),
  ('Плащ ночи','armor','cloak',NULL,4,16,20,12,'DEX',2,44),
  ('Плащ стрелы','armor','cloak',NULL,5,21,25,17,'DEX',2,68),
  ('Плащ фантома','armor','cloak',NULL,6,26,30,23,'DEX',3,100),
  ('Плащ тени','armor','cloak',NULL,7,31,35,30,'DEX',3,142),
  ('Плащ звёзд','armor','cloak',NULL,8,36,40,38,'DEX',4,192),
  ('Плащ королей','armor','cloak',NULL,9,41,45,48,'DEX',4,252),
  ('Плащ вечности','armor','cloak',NULL,10,46,50,59,'DEX',5,325),
  ('Кольчужный камизоль','armor','scale',NULL,1,1,5,6,'VIT',1,9),
  ('Чешуя нагрудник','armor','scale',NULL,2,6,10,11,'VIT',1,20),
  ('Чешуйчатый панцирь','armor','scale',NULL,3,11,15,17,'VIT',2,38),
  ('Ламелярный доспех','armor','scale',NULL,4,16,20,24,'VIT',2,64),
  ('Чешуя дракона','armor','scale',NULL,5,21,25,32,'VIT',2,98),
  ('Тяжёлая чешуя','armor','scale',NULL,6,26,30,42,'VIT',3,144),
  ('Чешуйчатый колосс','armor','scale',NULL,7,31,35,53,'VIT',3,204),
  ('Панцирь змея','armor','scale',NULL,8,36,40,65,'VIT',4,276),
  ('Чешуя предков','armor','scale',NULL,9,41,45,79,'VIT',4,360),
  ('Чешуя миров','armor','scale',NULL,10,46,50,95,'VIT',5,458),
  ('Костяной нагрудник','armor','bone',NULL,1,1,5,5,'VIT',1,8),
  ('Кости мертвеца','armor','bone',NULL,2,6,10,9,'VIT',1,17),
  ('Костяной доспех','armor','bone',NULL,3,11,15,14,'VIT',2,32),
  ('Ритуальные кости','armor','bone',NULL,4,16,20,20,'VIT',2,54),
  ('Костяной страж','armor','bone',NULL,5,21,25,27,'VIT',2,82),
  ('Доспех некроманта','armor','bone',NULL,6,26,30,35,'VIT',3,120),
  ('Кости великана','armor','bone',NULL,7,31,35,45,'VIT',3,170),
  ('Костяной титан','armor','bone',NULL,8,36,40,56,'VIT',4,230),
  ('Трон из костей','armor','bone',NULL,9,41,45,69,'VIT',4,302),
  ('Кости прародителя','armor','bone',NULL,10,46,50,84,'VIT',5,388),
  ('Шёлковая рубаха','armor','silks',NULL,1,1,5,1,'CHA',1,8),
  ('Придворная накидка','armor','silks',NULL,2,6,10,2,'CHA',1,17),
  ('Шёлк дипломата','armor','silks',NULL,3,11,15,3,'CHA',2,32),
  ('Мантия купца','armor','silks',NULL,4,16,20,4,'CHA',2,52),
  ('Наряд визиря','armor','silks',NULL,5,21,25,5,'CHA',2,80),
  ('Шёлк знати','armor','silks',NULL,6,26,30,7,'CHA',3,118),
  ('Одеяние патриция','armor','silks',NULL,7,31,35,9,'CHA',3,168),
  ('Королевский шёлк','armor','silks',NULL,8,36,40,11,'CHA',4,228),
  ('Шёлк империи','armor','silks',NULL,9,41,45,14,'CHA',4,300),
  ('Ткань судьбы','armor','silks',NULL,10,46,50,17,'CHA',5,385);

-- ── ACCESSORIES ──────────────────────────────────────────────
INSERT INTO item_base_templates
  (name, item_type, subtype, attack_type, tier, level_min, level_max,
   stat1_type, stat1_value, stat2_type, stat2_value, base_price)
VALUES
  ('Простое кольцо','ring','ring',NULL,1,1,5,'STR',1,NULL,0,5),
  ('Железное кольцо','ring','ring',NULL,2,6,10,'STR',1,'VIT',1,12),
  ('Кольцо силы','ring','ring',NULL,3,11,15,'STR',2,'VIT',1,24),
  ('Стальное кольцо','ring','ring',NULL,4,16,20,'STR',2,'VIT',2,40),
  ('Кольцо воина','ring','ring',NULL,5,21,25,'STR',3,'VIT',2,62),
  ('Кольцо чемпиона','ring','ring',NULL,6,26,30,'STR',3,'VIT',3,92),
  ('Кольцо берсерка','ring','ring',NULL,7,31,35,'STR',4,'VIT',3,130),
  ('Кольцо предка','ring','ring',NULL,8,36,40,'STR',4,'VIT',4,178),
  ('Кольцо легенды','ring','ring',NULL,9,41,45,'STR',5,'VIT',4,235),
  ('Кольцо вечности','ring','ring',NULL,10,46,50,'STR',5,'VIT',5,305),
  ('Медное кольцо','ring','ring',NULL,1,1,5,'DEX',1,NULL,0,5),
  ('Кольцо ловкача','ring','ring',NULL,2,6,10,'DEX',1,'INT',1,12),
  ('Кольцо лучника','ring','ring',NULL,3,11,15,'DEX',2,'INT',1,24),
  ('Кольцо охотника','ring','ring',NULL,4,16,20,'DEX',2,'INT',2,40),
  ('Кольцо следопыта','ring','ring',NULL,5,21,25,'DEX',3,'INT',2,62),
  ('Кольцо стрелка','ring','ring',NULL,6,26,30,'DEX',3,'INT',3,92),
  ('Кольцо призрака','ring','ring',NULL,7,31,35,'DEX',4,'INT',3,130),
  ('Кольцо тени','ring','ring',NULL,8,36,40,'DEX',4,'INT',4,178),
  ('Кольцо мастера','ring','ring',NULL,9,41,45,'DEX',5,'INT',4,235),
  ('Кольцо судьбы','ring','ring',NULL,10,46,50,'DEX',5,'INT',5,305),
  ('Простой амулет','amulet','amulet',NULL,1,1,5,'VIT',1,NULL,0,6),
  ('Амулет стойкости','amulet','amulet',NULL,2,6,10,'VIT',1,'STR',1,14),
  ('Медальон воина','amulet','amulet',NULL,3,11,15,'VIT',2,'STR',1,28),
  ('Амулет защиты','amulet','amulet',NULL,4,16,20,'VIT',2,'STR',2,46),
  ('Медальон стражника','amulet','amulet',NULL,5,21,25,'VIT',3,'STR',2,72),
  ('Амулет паладина','amulet','amulet',NULL,6,26,30,'VIT',3,'STR',3,106),
  ('Амулет хранителя','amulet','amulet',NULL,7,31,35,'VIT',4,'STR',3,150),
  ('Амулет бессмертия','amulet','amulet',NULL,8,36,40,'VIT',4,'STR',4,205),
  ('Амулет титана','amulet','amulet',NULL,9,41,45,'VIT',5,'STR',4,272),
  ('Амулет богов','amulet','amulet',NULL,10,46,50,'VIT',5,'STR',5,352),
  ('Магический амулет','amulet','amulet',NULL,1,1,5,'INT',1,NULL,0,6),
  ('Амулет мага','amulet','amulet',NULL,2,6,10,'INT',1,'DEX',1,14),
  ('Медальон тайн','amulet','amulet',NULL,3,11,15,'INT',2,'DEX',1,28),
  ('Амулет знаний','amulet','amulet',NULL,4,16,20,'INT',2,'DEX',2,46),
  ('Амулет архимага','amulet','amulet',NULL,5,21,25,'INT',3,'DEX',2,72),
  ('Амулет пророка','amulet','amulet',NULL,6,26,30,'INT',3,'DEX',3,106),
  ('Амулет звёзд','amulet','amulet',NULL,7,31,35,'INT',4,'DEX',3,150),
  ('Амулет вечности','amulet','amulet',NULL,8,36,40,'INT',4,'DEX',4,205),
  ('Амулет бездны','amulet','amulet',NULL,9,41,45,'INT',5,'DEX',4,272),
  ('Амулет Творения','amulet','amulet',NULL,10,46,50,'INT',5,'DEX',5,352),
  ('Торговый амулет','amulet','amulet',NULL,1,1,5,'CHA',1,NULL,0,6),
  ('Амулет купца','amulet','amulet',NULL,2,6,10,'CHA',1,'LUK',1,14),
  ('Медальон торговца','amulet','amulet',NULL,3,11,15,'CHA',2,'LUK',1,28),
  ('Амулет удачи','amulet','amulet',NULL,4,16,20,'LUK',2,'CHA',2,46),
  ('Счастливый амулет','amulet','amulet',NULL,5,21,25,'LUK',3,'CHA',2,72),
  ('Амулет фортуны','amulet','amulet',NULL,6,26,30,'LUK',3,'CHA',3,106),
  ('Амулет судьбы','amulet','amulet',NULL,7,31,35,'LUK',4,'CHA',3,150),
  ('Амулет богини удачи','amulet','amulet',NULL,8,36,40,'LUK',4,'CHA',4,205),
  ('Амулет провидца','amulet','amulet',NULL,9,41,45,'LUK',5,'CHA',4,272),
  ('Амулет Вселенной','amulet','amulet',NULL,10,46,50,'LUK',5,'CHA',5,352);

-- ── ACCESSORIES (доп. кольца INT + LUK, 2×10 = 20) ────────────
INSERT INTO item_base_templates
  (name, item_type, subtype, attack_type, tier, level_min, level_max,
   stat1_type, stat1_value, stat2_type, stat2_value, base_price)
VALUES
  ('Кольцо мысли','ring','ring',NULL,1,1,5,'INT',1,NULL,0,5),
  ('Кольцо учёного','ring','ring',NULL,2,6,10,'INT',1,'VIT',1,12),
  ('Кольцо мага','ring','ring',NULL,3,11,15,'INT',2,'VIT',1,24),
  ('Кольцо аркана','ring','ring',NULL,4,16,20,'INT',2,'VIT',2,40),
  ('Кольцо чародея','ring','ring',NULL,5,21,25,'INT',3,'VIT',2,62),
  ('Кольцо архимага','ring','ring',NULL,6,26,30,'INT',3,'VIT',3,92),
  ('Кольцо тайн','ring','ring',NULL,7,31,35,'INT',4,'VIT',3,130),
  ('Кольцо бездны','ring','ring',NULL,8,36,40,'INT',4,'VIT',4,178),
  ('Кольцо звёзд','ring','ring',NULL,9,41,45,'INT',5,'VIT',4,235),
  ('Кольцо Творения','ring','ring',NULL,10,46,50,'INT',5,'VIT',5,305),
  ('Кольцо везения','ring','ring',NULL,1,1,5,'LUK',1,NULL,0,5),
  ('Кольцо фортуны','ring','ring',NULL,2,6,10,'LUK',1,'CHA',1,12),
  ('Кольцо удачи','ring','ring',NULL,3,11,15,'LUK',2,'CHA',1,24),
  ('Кольцо золота','ring','ring',NULL,4,16,20,'LUK',2,'CHA',2,40),
  ('Кольцо торговли','ring','ring',NULL,5,21,25,'LUK',3,'CHA',2,62),
  ('Кольцо наследия','ring','ring',NULL,6,26,30,'LUK',3,'CHA',3,92),
  ('Кольцо провидца','ring','ring',NULL,7,31,35,'LUK',4,'CHA',3,130),
  ('Кольцо мира','ring','ring',NULL,8,36,40,'LUK',4,'CHA',4,178),
  ('Кольцо короны','ring','ring',NULL,9,41,45,'LUK',5,'CHA',4,235),
  ('Кольцо вечной удачи','ring','ring',NULL,10,46,50,'LUK',5,'CHA',5,305);

-- ── МАГИЧЕСКИЕ СФЕРЫ (off-hand, аналог щита; колонки race/class после миграции 0043) ──
INSERT INTO item_base_templates
  (name, item_type, subtype, attack_type, tier, level_min, level_max,
   dmg_min, dmg_max, attack_speed, armor_base, stat1_type, stat1_value, base_price,
   required_race, required_class)
VALUES
  ('Стеклянная сфера','weapon','orb','magic',1,1,5,0,0,10,2,'INT',1,8,NULL,NULL),
  ('Сфера ученика','weapon','orb','magic',2,6,10,0,0,10,4,'INT',1,17,NULL,NULL),
  ('Осколок маны','weapon','orb','magic',3,11,15,0,0,10,7,'INT',2,32,NULL,NULL),
  ('Сфера фокусировки','weapon','orb','magic',4,16,20,0,0,10,10,'INT',2,52,NULL,NULL),
  ('Сфера дуги','weapon','orb','magic',5,21,25,0,0,10,14,'INT',2,80,NULL,NULL),
  ('Сфера вихря','weapon','orb','magic',6,26,30,0,0,10,18,'INT',3,118,NULL,NULL),
  ('Сфера наставника','weapon','orb','magic',7,31,35,0,0,10,24,'INT',3,170,NULL,NULL),
  ('Сфера бездны','weapon','orb','magic',8,36,40,0,0,10,30,'INT',4,230,NULL,NULL),
  ('Сфера затмения','weapon','orb','magic',9,41,45,0,0,10,37,'INT',4,302,NULL,NULL),
  ('Сфера Творения','weapon','orb','magic',10,46,50,0,0,10,45,'INT',5,390,NULL,NULL);

-- ── Усиленные предметы: раса (тиры 5 и 9) и класс (тиры 4 и 10) ─────────────────
INSERT INTO item_base_templates
  (name, item_type, subtype, attack_type, tier, level_min, level_max,
   dmg_min, dmg_max, attack_speed, armor_base, stat1_type, stat1_value, base_price,
   required_race, required_class)
VALUES
  ('Клинок лесного народа','weapon','one_hand','melee',5,21,25,17,27,5,0,'STR',3,128,2,NULL),
  ('Клинок феячьего двора','weapon','one_hand','melee',9,41,45,43,63,5,0,'STR',5,472,7,NULL),
  ('Клинок варварской кузни','weapon','one_hand','melee',4,16,20,14,21,5,0,'STR',3,81,NULL,2),
  ('Клинок тихой смерти','weapon','one_hand','melee',10,46,50,53,78,5,0,'STR',6,610,NULL,5),
  ('Топор зверолюда','weapon','two_hand','melee',5,21,25,22,33,6,0,'STR',3,138,3,NULL),
  ('Секира пламени бездны','weapon','two_hand','melee',9,41,45,53,79,6,0,'STR',5,518,6,NULL),
  ('Двуручник рыцарского ордена','weapon','two_hand','melee',4,16,20,17,26,6,0,'STR',3,92,NULL,1),
  ('Топор вечного поля боя','weapon','two_hand','melee',10,46,50,66,98,6,0,'STR',6,668,NULL,2),
  ('Лук серебряных крон','weapon','bow','ranged',5,21,25,15,23,4,0,'DEX',3,115,2,NULL),
  ('Лук имперского легиона','weapon','bow','ranged',9,41,45,36,54,4,0,'DEX',5,438,1,NULL),
  ('Лук мастера дальнего выстрела','weapon','bow','ranged',4,16,20,12,18,4,0,'DEX',3,75,NULL,3),
  ('Лук теневого убийцы','weapon','bow','ranged',10,46,50,44,67,4,0,'DEX',6,565,NULL,5),
  ('Посох лунного эльфа','weapon','staff','magic',5,21,25,12,21,7,0,'INT',3,124,2,NULL),
  ('Посох сжигаемой души','weapon','staff','magic',9,41,45,29,49,7,0,'INT',5,466,6,NULL),
  ('Посох архимагистра','weapon','staff','magic',4,16,20,9,16,7,0,'INT',3,78,NULL,4),
  ('Посох хранителя жизни','weapon','staff','magic',10,46,50,36,61,7,0,'INT',6,605,NULL,6),
  ('Щит имперской стражи','weapon','offhand','melee',5,21,25,0,0,10,26,'VIT',3,92,1,NULL),
  ('Щит перворождённого света','weapon','offhand','melee',9,41,45,0,0,10,69,'VIT',5,352,4,NULL),
  ('Щит братства плит','weapon','offhand','melee',4,16,20,0,0,10,19,'VIT',3,58,NULL,1),
  ('Щит последнего обряда','weapon','offhand','melee',10,46,50,0,0,10,85,'VIT',6,455,NULL,6),
  ('Сфера небесного откровения','weapon','orb','magic',5,21,25,0,0,10,16,'INT',3,92,4,NULL),
  ('Сфера кровавого лунного затмения','weapon','orb','magic',9,41,45,0,0,10,43,'INT',5,348,5,NULL),
  ('Сфера первого заклинания','weapon','orb','magic',4,16,20,0,0,10,12,'INT',3,58,NULL,4),
  ('Сфера закрытой раны','weapon','orb','magic',10,46,50,0,0,10,52,'INT',6,449,NULL,6);

INSERT INTO item_base_templates
  (name, item_type, subtype, attack_type, tier, level_min, level_max,
   armor_base, stat1_type, stat1_value, base_price,
   required_race, required_class)
VALUES
  ('Латы звериной ярости','armor','medium',NULL,5,21,25,36,'VIT',3,104,3,NULL),
  ('Кольчуга ночного охотника','armor','medium',NULL,9,41,45,94,'VIT',5,390,5,NULL),
  ('Панцирь ордена','armor','medium',NULL,4,16,20,26,'VIT',3,64,NULL,1),
  ('Доспех полевого маршала','armor','medium',NULL,10,46,50,115,'VIT',6,504,NULL,2);

INSERT INTO item_base_templates
  (name, item_type, subtype, attack_type, tier, level_min, level_max,
   stat1_type, stat1_value, stat2_type, stat2_value, base_price,
   required_race, required_class)
VALUES
  ('Кольцо родовой печати','ring','ring',NULL,5,21,25,'STR',3,'VIT',2,72,1,NULL),
  ('Кольцо лунного шёпота','ring','ring',NULL,9,41,45,'STR',6,'VIT',5,272,7,NULL),
  ('Кольцо золотой подписи','ring','ring',NULL,4,16,20,'STR',3,'VIT',2,46,NULL,7),
  ('Кольцо исцеляющего круга','ring','ring',NULL,10,46,50,'STR',6,'VIT',6,352,NULL,6),
  ('Амулет нисхождения','amulet','amulet',NULL,5,21,25,'VIT',4,'STR',3,84,4,NULL),
  ('Амулет нижнего договора','amulet','amulet',NULL,9,41,45,'VIT',6,'STR',5,314,6,NULL),
  ('Амулет четырёх стихий','amulet','amulet',NULL,4,16,20,'INT',3,'DEX',2,54,NULL,4),
  ('Амулет торговых дорог','amulet','amulet',NULL,10,46,50,'LUK',6,'CHA',6,406,NULL,7);

-- Verify
SELECT item_type, subtype, COUNT(*) as cnt,
       MIN(tier) as tier_min, MAX(tier) as tier_max
FROM item_base_templates
GROUP BY item_type, subtype ORDER BY item_type, subtype;

COMMIT;