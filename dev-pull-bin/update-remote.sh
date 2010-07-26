NAME=`whoami`
MUTEX="/tmp/${NAME}-dpmutex-${REMOTE_DB}";
NOW=`date '+%s'`
if [ "${REMOTE_PROC_DB-n}" != "n" ]; then
  MUTEX="/tmp/${NAME}-dpmutex-${REMOTE_PROC_DB}";
fi

while [ -f $MUTEX ]; do
  if [ -f $MUTEX ]; then
    THEN=`cat $MUTEX`
    DELTA=$((NOW-THEN))
    if [ $DELTA -gt 3600 ]; then # 1h = too long
      echo "Other-dev pull took too long, going ahead anyway"
      date '+%s' > $MUTEX
    else
      echo "Waiting for other dev-pull to finish..."
      sleep 5
    fi
  fi
done

if [ ! -f $MUTEX ]; then
  date '+%s' > $MUTEX
fi

cd $REMOTE_GIT_DIR
echo "Dumping database"
mysqldump -h $REMOTE_HOST -P $REMOTE_PORT -u $REMOTE_USER -p"$REMOTE_PASS" $REMOTE_DB > dump.sql

if [ "${REMOTE_PROC_DB-n}" != "n" ]; then
  echo "Emptying processing database"
  mysqldump -h $REMOTE_PROC_HOST -P $REMOTE_PROC_PORT -u $REMOTE_PROC_USER -p"$REMOTE_PROC_PASS" --add-drop-table --force --no-data $REMOTE_PROC_DB | grep ^DROP | mysql -h $REMOTE_PROC_HOST -P $REMOTE_PROC_PORT -u $REMOTE_PROC_USER -p"$REMOTE_PROC_PASS" $REMOTE_PROC_DB
  echo "Loading data into processing database"
  mysql -h $REMOTE_PROC_HOST -P $REMOTE_PROC_PORT -u $REMOTE_PROC_USER -p"$REMOTE_PROC_PASS" $REMOTE_PROC_DB < dump.sql
  echo "Processing..."
  echo "UPDATE ${TABLE_PREFIX}users SET pass=MD5('pass') WHERE uid!=0;" |
    mysql -h $REMOTE_PROC_HOST -P $REMOTE_PROC_PORT -u $REMOTE_PROC_USER -p"$REMOTE_PROC_PASS" $REMOTE_PROC_DB;
  # Looping over them to ensure that a failure on one because it doesn't exist doesn't affect the others
  TRUNCATE_TABLES="cache cache_block cache_coder cache_content cache_filter cache_form cache_menu cache_page cache_update cache_views cache_views_data sessions watchdog"
  for TRUNCATE_TABLE in $TRUNCATE_TABLES; do
    echo "TRUNCATE TABLE ${TABLE_PREFIX}${TRUNCATE_TABLE};" |
      mysql -h $REMOTE_PROC_HOST -P $REMOTE_PROC_PORT -u $REMOTE_PROC_USER -p"$REMOTE_PROC_PASS" $REMOTE_PROC_DB;
  done
  echo "Dumping processing database"
  mysqldump -h $REMOTE_PROC_HOST -P $REMOTE_PROC_PORT -u $REMOTE_PROC_USER -p"$REMOTE_PROC_PASS" $REMOTE_PROC_DB > dump.sql
fi

echo "Committing the new dump"
git add dump.sql
git commit -m "New dump added `date +"%Y-%m-%d %H:%M:%S"`"

rm $MUTEX