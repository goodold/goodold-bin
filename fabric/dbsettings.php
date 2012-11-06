<?php
if (is_file('wp-config.php')) {
  // Wordpress
  $settings_file = 'wp-config.php';
  // Create a temporary wp-settings.php and trick WP to load that since
  // loading the original file here breaks stuff.
  $temp_dir = sys_get_temp_dir() . '/';
  file_put_contents($temp_dir . 'wp-settings.php', '');
  define('ABSPATH', $temp_dir);
  include($settings_file);
  $json = json_encode(array('database' => DB_NAME, 'username' => DB_USER, 'password' => DB_PASSWORD, 'host' => DB_HOST));
  exit(json_encode(array('database' => DB_NAME, 'username' => DB_USER, 'password' => DB_PASSWORD, 'host' => DB_HOST)));
}
else if (is_file('sites/default/settings.php')) {
  chdir('sites/default');
  include('settings.php');
  if (isset($db_url)) {
    // Drupal 6
    $parsed_db_url = parse_url($db_url);
    $settings['database'] = substr($parsed_db_url['path'], 1);
    $settings['password'] = $parsed_db_url['pass'];
    $settings['username'] = $parsed_db_url['user'];
    $settings['host'] = $parsed_db_url['host'];
    if (isset($parsed_db_url['port'])) {
      $settings['port'] = $parsed_db_url['port'];
    }
    $settings['db_prefix'] = $db_prefix;
    exit(json_encode($settings));
  }
  else {
    // Drupal 7
    exit(json_encode($databases['default']['default']));
  }
}

