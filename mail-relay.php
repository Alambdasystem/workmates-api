<?php
// Narrow signed relay: invitation emails only. Secret lives outside public_html.
header('Content-Type: application/json');
header('Cache-Control: no-store');
function fail_request($code) { http_response_code($code); echo json_encode(['accepted'=>false]); exit; }
if ($_SERVER['REQUEST_METHOD'] !== 'POST') fail_request(405);
$raw=file_get_contents('php://input', false, null, 0, 12000);
$stamp=$_SERVER['HTTP_X_WORKMATES_TIME'] ?? '';
$sig=$_SERVER['HTTP_X_WORKMATES_SIGNATURE'] ?? '';
$secret=trim(file_get_contents(dirname(__DIR__).'/workmates-private/mail-secret'));
if (!$secret || !ctype_digit($stamp) || abs(time()-(int)$stamp)>120 || !hash_equals(hash_hmac('sha256',$stamp.'.'.$raw,$secret),$sig)) fail_request(403);
$d=json_decode($raw,true);
if (!is_array($d) || !filter_var($d['to'] ?? '',FILTER_VALIDATE_EMAIL) || preg_match('/[\r\n]/',$d['to'])) fail_request(400);
if (!preg_match('~^https://workmates-core\.onrender\.com/\#invite=[A-Za-z0-9_-]+&email=[A-Za-z0-9%_.@+\-]*$~D',$d['url'] ?? '')) fail_request(400);
$inviter=substr(preg_replace('/[\r\n\x00-\x1f]/',' ',(string)($d['inviter'] ?? 'Your teammate')),0,100);
$group=substr(preg_replace('/[\r\n\x00-\x1f]/',' ',(string)($d['group'] ?? 'a group')),0,200);
// Deduplicate identical signed requests. This directory is outside the web root.
$dir=dirname(__DIR__).'/workmates-private/mail-receipts';
if (!is_dir($dir)) mkdir($dir,0700,true);
$path=$dir.'/'.hash('sha256',$stamp.'.'.$raw);
$lock=fopen($path,'c+');if (!$lock || !flock($lock,LOCK_EX)) fail_request(503);
$prior=stream_get_contents($lock);
if ($prior==='accepted') { echo json_encode(['accepted'=>true]);exit; }
foreach(glob($dir.'/*') as $old) { if(filemtime($old)<time()-86400) @unlink($old); }
$body=$inviter." invited you to join ".$group." in Workmates.\n\nOpen your private invitation:\n".$d['url']."\n\nThis invitation expires in seven days and can be used once. New users choose their own password. Existing users keep theirs.\n\nWorkmates by Alambda Systems\n";
$accepted=mail($d['to'],'Your Workmates group invitation',$body,"From: Workmates <notifications@alambda.systems>\r\nContent-Type: text/plain; charset=UTF-8\r\n");
if ($accepted){rewind($lock);ftruncate($lock,0);fwrite($lock,'accepted');}
flock($lock,LOCK_UN);fclose($lock);
if (!$accepted) http_response_code(502);
echo json_encode(['accepted'=>$accepted]);
