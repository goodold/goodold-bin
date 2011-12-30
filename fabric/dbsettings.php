<?php 
if (is_file('wp-config.php')) {
  // Wordpress
  $settings_file = 'wp-config.php';
  include($settings_file);
  exit(json_encode(array('database' => DB_NAME, 'username' => DB_USER, 'password' => DB_PASSWORD, 'host' => DB_HOST)));
}
else if (is_file('sites/default/settings.php')) {
  chdir('sites/default');
  if (isset($db_url)) {
    // Drupal 6
    include('settings.php');
    $parsed_db_url = parse_url($db_url);
    $parsed_db_url['database'] = substr($parsed_db_url['path'], 1);
    $parsed_db_url['password'] = $parsed_db_url['pass'];
    $parsed_db_url['username'] = $parsed_db_url['user'];
    $parsed_db_url['prefix'] = $db_prefix;
    exit(json_encode($parsed_db_url));
  }
  else {
    // Drupal 7
    include('settings.php');
    exit(json_encode($databases['default']['default']));
  }
}

