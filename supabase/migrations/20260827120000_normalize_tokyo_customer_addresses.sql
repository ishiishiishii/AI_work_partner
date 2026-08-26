-- Tokyo demo customers use valid Chiyoda City town/chome names and GSI
-- representative points. They remain fictional companies; these coordinates
-- are intended for area-to-area route planning, not building-level visits.
with normalized(
  customer_id, customer_name, old_location, new_location,
  latitude, longitude, place_id
) as (
  values
    (11,  '星野商事株式会社',       '東京都千代田区九段1-18-15',  '東京都千代田区九段北1丁目',       35.696655, 139.750656, 'gsi:東京都千代田区九段北一丁目'),
    (13,  '太陽工業株式会社',       '東京都千代田区神田2-12-5',   '東京都千代田区内神田2丁目',       35.690601, 139.768021, 'gsi:東京都千代田区内神田二丁目'),
    (27,  '株式会社大東興業',       '東京都千代田区九段6-12-9',   '東京都千代田区九段南4丁目',       35.691250, 139.738678, 'gsi:東京都千代田区九段南四丁目'),
    (37,  '株式会社中央産業',       '東京都千代田区神田2-28-10',  '東京都千代田区神田神保町2丁目', 35.696636, 139.756454, 'gsi:東京都千代田区神田神保町二丁目'),
    (53,  '株式会社稲穂物流',       '東京都千代田区丸の内6-30-7', '東京都千代田区丸の内1丁目',       35.681561, 139.767197, 'gsi:東京都千代田区丸の内一丁目'),
    (65,  '桜庭商事株式会社',       '東京都千代田区丸の内7-20-5', '東京都千代田区丸の内2丁目',       35.680023, 139.763443, 'gsi:東京都千代田区丸の内二丁目'),
    (74,  '有限会社北斗フーズ',   '東京都千代田区神田4-27-13',  '東京都千代田区神田佐久間町4丁目', 35.697659, 139.779831, 'gsi:東京都千代田区神田佐久間町四丁目'),
    (83,  '株式会社若葉フーズ',   '東京都千代田区丸の内3-28-9', '東京都千代田区丸の内3丁目',       35.676952, 139.763474, 'gsi:東京都千代田区丸の内三丁目'),
    (121, '磯辺運送有限会社',       '東京都千代田区丸の内1-12-10','東京都千代田区丸の内1丁目',       35.681561, 139.767197, 'gsi:東京都千代田区丸の内一丁目'),
    (123, '若草食品株式会社',       '東京都千代田区九段2-30-12',  '東京都千代田区九段南2丁目',       35.693142, 139.745697, 'gsi:東京都千代田区九段南二丁目'),
    (128, '株式会社早苗食品',       '東京都千代田区丸の内7-19-8', '東京都千代田区丸の内2丁目',       35.680023, 139.763443, 'gsi:東京都千代田区丸の内二丁目'),
    (243, '白鷺フードサービス株式会社', '東京都千代田区神田3-26-1', '東京都千代田区神田神保町3丁目', 35.695366, 139.754272, 'gsi:東京都千代田区神田神保町三丁目')
)
update customer c
set location = n.new_location
from normalized n
where c.customer_id = n.customer_id
  and c.customer_name = n.customer_name
  and c.location = n.old_location;

-- The location trigger clears route coordinates when an address changes, so
-- populate both route-planning and map coordinate columns in a second update.
with normalized(
  customer_id, customer_name, location, latitude, longitude, place_id
) as (
  values
    (11,  '星野商事株式会社',       '東京都千代田区九段北1丁目',       35.696655, 139.750656, 'gsi:東京都千代田区九段北一丁目'),
    (13,  '太陽工業株式会社',       '東京都千代田区内神田2丁目',       35.690601, 139.768021, 'gsi:東京都千代田区内神田二丁目'),
    (27,  '株式会社大東興業',       '東京都千代田区九段南4丁目',       35.691250, 139.738678, 'gsi:東京都千代田区九段南四丁目'),
    (37,  '株式会社中央産業',       '東京都千代田区神田神保町2丁目', 35.696636, 139.756454, 'gsi:東京都千代田区神田神保町二丁目'),
    (53,  '株式会社稲穂物流',       '東京都千代田区丸の内1丁目',       35.681561, 139.767197, 'gsi:東京都千代田区丸の内一丁目'),
    (65,  '桜庭商事株式会社',       '東京都千代田区丸の内2丁目',       35.680023, 139.763443, 'gsi:東京都千代田区丸の内二丁目'),
    (74,  '有限会社北斗フーズ',   '東京都千代田区神田佐久間町4丁目', 35.697659, 139.779831, 'gsi:東京都千代田区神田佐久間町四丁目'),
    (83,  '株式会社若葉フーズ',   '東京都千代田区丸の内3丁目',       35.676952, 139.763474, 'gsi:東京都千代田区丸の内三丁目'),
    (121, '磯辺運送有限会社',       '東京都千代田区丸の内1丁目',       35.681561, 139.767197, 'gsi:東京都千代田区丸の内一丁目'),
    (123, '若草食品株式会社',       '東京都千代田区九段南2丁目',       35.693142, 139.745697, 'gsi:東京都千代田区九段南二丁目'),
    (128, '株式会社早苗食品',       '東京都千代田区丸の内2丁目',       35.680023, 139.763443, 'gsi:東京都千代田区丸の内二丁目'),
    (243, '白鷺フードサービス株式会社', '東京都千代田区神田神保町3丁目', 35.695366, 139.754272, 'gsi:東京都千代田区神田神保町三丁目')
)
update customer c
set latitude = n.latitude,
    longitude = n.longitude,
    place_id = n.place_id,
    geocoding_status = 'success',
    geocode_accuracy = 'chome;source=gsi',
    geocoded_at = current_timestamp,
    lat = n.latitude,
    lng = n.longitude
from normalized n
where c.customer_id = n.customer_id
  and c.customer_name = n.customer_name
  and c.location = n.location;
