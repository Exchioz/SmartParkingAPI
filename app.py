from flask import Flask, request, jsonify
from flask_mysqldb import MySQL
import yaml
import datetime
import bcrypt
import re

app = Flask(__name__)

db = yaml.load(open('db.yaml'), Loader=yaml.FullLoader)
app.config['MYSQL_HOST'] = db['mysql_host']
app.config['MYSQL_USER'] = db['mysql_user']
app.config['MYSQL_PASSWORD'] = db['mysql_password']
app.config['MYSQL_DB'] = db['mysql_db']

mysql = MySQL(app)

#--Function--#
def is_valid_email(email):
    pattern = r'^[\w\.-]+@[a-zA-Z\d\.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def is_valid_phone_number(telp):
    return telp.isdigit() and len(telp) >= 10

def is_valid_plate_number(platenumber):
    pattern = r'^[A-Z0-9]{1,8}$'
    return re.match(pattern, platenumber) is not None

def check_email_exists(email, exclude_userid=None):
    cur = mysql.connection.cursor()
    if exclude_userid:
        cur.execute("SELECT id FROM users WHERE email = %s AND id != %s", (email, exclude_userid,))
    else:
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    existing_email = cur.fetchone()
    cur.close()
    return existing_email

def check_telp_exists(telp, exclude_userid=None):
    cur = mysql.connection.cursor()
    if exclude_userid:
        cur.execute("SELECT id FROM users WHERE telp = %s AND id != %s", (telp, exclude_userid,))
    else:
        cur.execute("SELECT id FROM users WHERE telp = %s", (telp,))
    existing_telp = cur.fetchone()
    cur.close()
    return existing_telp

def check_platenumber_exists(platenumber, exclude_userid=None):
    cur = mysql.connection.cursor()
    if exclude_userid:
        cur.execute("SELECT id FROM users WHERE platenomor = %s AND id != %s", (platenumber, exclude_userid,))
    else:
        cur.execute("SELECT id FROM users WHERE platenomor = %s", (platenumber,))
    existing_platenumber = cur.fetchone()
    cur.close()
    return existing_platenumber


#--Routes--#
@app.route('/reservasi', methods=['POST'])
def reservasi():
    
    user_id = request.json['user_id']
    tempat_parkir_id = request.json['parkir_id']
    waktu = datetime.datetime.now()
    waktu_reservasi = waktu.strftime('%Y-%m-%d %H:%M:%S')
    waktu_expired = waktu + datetime.timedelta(hours=1)
    waktu_akhir = waktu_expired.strftime('%Y-%m-%d %H:%M:%S')
    status = "Pending"

    try:
        cur = mysql.connection.cursor()

        cur.execute("SELECT tersedia FROM tempat_parkir WHERE id = %s", [tempat_parkir_id])
        tersedia = cur.fetchone()[0]
        if tersedia <= 0:
            return jsonify({'message': 'Tempat parkir tidak tersedia.'}), 400
        
        cur.execute("INSERT INTO reservasi (user_id, parkir_id, waktu_awal, waktu_akhir, status) VALUES (%s, %s, %s, %s, %s)", (user_id, tempat_parkir_id, waktu_reservasi, waktu_akhir, status))
        cur.execute("SELECT LAST_INSERT_ID()")
        last_row_id = cur.fetchone()[0]

        cur.execute("UPDATE tempat_parkir SET tersedia = tersedia - 1 WHERE id = %s", [tempat_parkir_id])
        cur.execute("CREATE EVENT IF NOT EXISTS cancel_reservasi_" + str(last_row_id) + " ON SCHEDULE AT '" + waktu_akhir + "' DO BEGIN UPDATE reservasi SET status = 'Canceled' WHERE id = " + str(last_row_id) + "; UPDATE tempat_parkir SET tersedia = tersedia + 1 WHERE id = (SELECT parkir_id FROM reservasi WHERE id = " + str(last_row_id) + "); END")
        mysql.connection.commit()

        return jsonify({'message': 'Reservasi berhasil.'}), 200
    
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'message': 'Terjadi kesalahan saat melakukan reservasi.', 'error': str(e)}), 500


@app.route('/cancel_reservasi/<int:user_id>', methods=['PUT'])
def cancel_reservasi(user_id):
    try:
        cur = mysql.connection.cursor()

        cur.execute("SELECT id, parkir_id FROM reservasi WHERE user_id = %s AND status = 'Pending' ORDER BY id DESC LIMIT 1", [user_id])
        reservasi_data = cur.fetchone()
        if not reservasi_data:
            return jsonify({'message': 'Tidak ada reservasi yang dapat dibatalkan untuk pengguna ini.'}), 404

        reservasi_id, parkir_id = reservasi_data

        cur.execute("DROP EVENT IF EXISTS cancel_reservasi_" + str(reservasi_id))
        cur.execute("UPDATE reservasi SET status = 'Canceled' WHERE id = %s", [reservasi_id])
        cur.execute("UPDATE tempat_parkir SET tersedia = tersedia + 1 WHERE id = %s", [parkir_id])
        mysql.connection.commit()

        return jsonify({'message': 'Reservasi berhasil dibatalkan'}), 200
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({'message': str(e)}), 500


@app.route('/login', methods=['POST'])
def login():
    cur = mysql.connection.cursor()
    email = request.json['email']
    password = request.json['password'].encode('utf-8')
    response = {}

    if not email or not password:
        return jsonify({'message': 'Email dan password tidak boleh kosong.'}), 400
    if not is_valid_email(email):
        return jsonify({'message': 'Email tidak valid.'}), 400
    
    try:
        cur.execute("SELECT id, password FROM users WHERE email = %s", [email])
        user = cur.fetchone()
    finally:
        cur.close()
    
    if user and bcrypt.checkpw(password, user[1].encode('utf-8')):
        status = 200
        response['message'] = 'Login berhasil.'
        response['id'] = user[0]
    elif user:
        status = 400
        response['message'] = 'Password salah.'
    else:
        status = 400
        response['message'] = 'Pengguna tidak ditemukan.'
    
    return jsonify(response),status


@app.route('/users', methods=['POST'])
def get_users():
    cur = mysql.connection.cursor()
    id = request.json['id']
    cur.execute("SELECT * FROM users WHERE id = %s", [id])
    user = cur.fetchone()
    cur.close()

    if user:
        saldo_str = "{:,.0f}".format(user[6]).replace(',', '.')
        
        user_data = {
            'email': user[1],
            'telp': user[2],
            'nama': user[4],
            'platenomor': user[5],
            'saldo': saldo_str
        }
        return jsonify(user_data), 200
    else:
        return jsonify({'message': 'Pengguna tidak ditemukan.'}), 404
    
@app.route('/tempat_parkir', methods=['GET'])
def get_tempat_parkir():
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, namatempat, alamat, longg, lat, harga, kapasitas, tersedia FROM tempat_parkir")
    hasil = cur.fetchall()
    cur.close()
    
    data_tempat_parkir = []
    for row in hasil:
        harga_str = "{:,.0f}".format(row[5]).replace(',', '.')

        data_tempat_parkir.append({
            'id': row[0],
            'namatempat': row[1],
            'alamat': row[2],
            'harga': harga_str,
            'tersedia': row[7]
        })
    
    return jsonify(data_tempat_parkir), 200

@app.route('/tempat_parkir/<int:id>', methods=['GET'])
def detail_tempat_parkir(id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT id, namatempat, alamat, longg, lat, harga, kapasitas, tersedia FROM tempat_parkir WHERE id = %s", (id,))
    tempat_parkir = cur.fetchone()
    cur.close()
    
    if tempat_parkir:
        harga_str = "{:,.0f}".format(tempat_parkir[5]).replace(',', '.')

        data_detail = {
            'id': tempat_parkir[0],
            'namatempat': tempat_parkir[1],
            'alamat': tempat_parkir[2],
            'longg': tempat_parkir[3],
            'lat': tempat_parkir[4],
            'harga': harga_str,
            'kapasitas': tempat_parkir[6],
            'tersedia': tempat_parkir[7]
        }
        return jsonify(data_detail), 200
    else:
        return jsonify({'message': 'Tempat parkir tidak ditemukan.'}), 404

@app.route('/getReservasiStatus', methods=['GET'])
def get_reservasi_status():
    try:
        cur = mysql.connection.cursor()
        user_id = request.args.get('userId')

        # Mendapatkan status reservasi terbaru berdasarkan user_id
        cur.execute("SELECT status FROM reservasi WHERE user_id = %s ORDER BY waktu_awal DESC LIMIT 1", [user_id])
        status = cur.fetchone()
        print("Debug Status:", status)

        if status:
            return jsonify({'status': status[0]}), 200
        else:
            return jsonify({'message': 'Reservasi tidak ditemukan.'}), 404
    except Exception as e:
        return jsonify({'message': 'Terjadi kesalahan saat mengambil status reservasi.', 'error': str(e)}), 500
    finally:
        if cur:
            cur.close()

@app.route('/updateUser', methods=['PUT'])
def update_user():
    cur = mysql.connection.cursor()
    userid = request.json['userid']
    email = request.json['email']
    telp = request.json['telp']
    nama = request.json['nama']
    platenumber = request.json['platenomor']
    
    # Validasi input
    if not userid or not email or not telp or not nama or not platenumber:
        return jsonify({'message': 'Kolom tidak boleh kosong.'}), 400
    if not is_valid_email(email):
        return jsonify({'message': 'Email tidak valid.'}), 400
    if not is_valid_phone_number(telp):
        return jsonify({'message': 'Nomor telepon tidak valid.'}), 400
    if not is_valid_plate_number(platenumber):
        return jsonify({'message': 'Nomor plat tidak valid.'}), 400

    # Check data if already exists
    existing_email = check_email_exists(email, exclude_userid=userid)
    if existing_email:
        return jsonify({'message': 'Email sudah digunakan.'}), 400
    existing_telp = check_telp_exists(telp, exclude_userid=userid)
    if existing_telp:
        return jsonify({'message': 'Nomor telepon sudah digunakan.'}), 400
    existing_platenumber = check_platenumber_exists(platenumber, exclude_userid=userid)
    if existing_platenumber:
        return jsonify({'message': 'Nomor plat sudah digunakan.'}), 400

    cur.execute("UPDATE users SET email = %s, telp=%s, nama = %s, platenomor = %s WHERE id = %s", (email, telp, nama, platenumber, userid))
    mysql.connection.commit()
    cur.close()

    return jsonify({'message': 'Data pengguna berhasil diperbarui.'}), 200

@app.route('/checkEmail', methods=['GET'])
def check_email():
    cur = mysql.connection.cursor()
    email = request.args.get('email')
    user_id = request.args.get('userId')

    cur.execute("SELECT email FROM users WHERE email = %s AND id != %s", (email, user_id))
    user = cur.fetchone()
    cur.close()

    if user:
        return jsonify({'message': 'Email sudah digunakan.'}), 400
    else:
        return jsonify({'message': 'Email tersedia.'}), 200
    
@app.route('/checkPlateNumber', methods=['GET'])
def check_plat_nomor():
    cur = mysql.connection.cursor()
    platenomor = request.args.get('plateNumber')
    user_id = request.args.get('userId')

    cur.execute("SELECT platenomor FROM users WHERE platenomor = %s AND id != %s", (platenomor, user_id))
    user = cur.fetchone()
    cur.close()

    if user:
        return jsonify({'message': 'Plat nomor sudah digunakan.'}), 400
    else:
        return jsonify({'message': 'Plat nomor tersedia.'}), 200
    
@app.route('/changePassword', methods=['PUT'])
def change_password():
    cur = mysql.connection.cursor()
    userid = request.json['userid']
    old_password = request.json['oldPassword'].encode('utf-8')
    new_password = request.json['newPassword'].encode('utf-8')
    new_password_confirm = request.json['confirmPassword'].encode('utf-8')

    if not old_password or not new_password or not new_password_confirm:
        return jsonify({'message': 'Kolom tidak boleh kosong.'}), 400
    
    if old_password == new_password:
        return jsonify({'message': 'Password baru tidak boleh sama dengan password lama.'}), 400
    
    if new_password != new_password_confirm:
        return jsonify({'message': 'Password baru tidak cocok.'}), 400
    
    if len(new_password) < 8:
        return jsonify({'message': 'Password baru harus memiliki minimal 8 karakter.'}), 400

    cur.execute("SELECT password FROM users WHERE id = %s", [userid])
    user = cur.fetchone()
    if not user:
        return jsonify({'message': 'Pengguna tidak ditemukan.'}), 404
    elif not bcrypt.checkpw(old_password, user[0].encode('utf-8')):
        return jsonify({'message': 'Password lama salah.'}), 400
    
    # Hash password baru
    hashed_new_password = bcrypt.hashpw(new_password, bcrypt.gensalt())

    cur.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_new_password, userid))
    mysql.connection.commit()
    cur.close()

    return jsonify({'message': 'Password berhasil diperbarui.'}), 200

@app.route('/signup', methods=['POST'])
def signup():
    try:
        data = request.json
        name = data.get('nama')
        email = data.get('email')
        telp = data.get('telp')
        password = data.get('password').encode('utf-8')
        password_confirm = data.get('password2').encode('utf-8')
        platenumber = data.get('platenumber')

        if not name or not email or not telp or not password or not password_confirm or not platenumber:
            return jsonify({'message': 'Kolom tidak boleh kosong.'}), 400
        if not is_valid_email(email):
            return jsonify({'message': 'Email tidak valid.'}), 400
        if not is_valid_phone_number(telp):
            return jsonify({'message': 'Nomor telepon tidak valid.'}), 400
        if not is_valid_plate_number(platenumber):
            return jsonify({'message': 'Nomor plat tidak valid.'}), 400
        if check_email_exists(email):
            return jsonify({'message': 'Email sudah digunakan.'}), 400
        if check_telp_exists(telp):
            return jsonify({'message': 'Nomor telepon sudah digunakan.'}), 400
        if password != password_confirm:
            return jsonify({'message': 'Password tidak cocok.'}), 400
        if len(password_confirm) < 8:
            return jsonify({'message': 'Password harus memiliki minimal 8 karakter.'}), 400
        if check_platenumber_exists(platenumber):
            return jsonify({'message': 'Nomor plat sudah digunakan.'}), 400

        hashed_password = bcrypt.hashpw(password_confirm, bcrypt.gensalt())
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO users (email, telp, password, nama, platenomor, saldo) VALUES (%s, %s, %s, %s, %s, %s)", (email, telp, hashed_password, name, platenumber, 0))
        mysql.connection.commit()
        cur.close()
        return jsonify({'message': 'Pendaftaran berhasil.'}), 200
    except Exception as e:
        return jsonify({'message': e}), 500
    

@app.route('/checkIn', methods=['POST'])
def check_in():
    try:
        cur = mysql.connection.cursor()
        plate_number = request.json['plateNumber']
        parkir_id = request.json['idParkir']

        # Check if the user has a reservation with the given plate number
        cur.execute("SELECT id FROM users WHERE platenomor = %s", [plate_number])
        user = cur.fetchone()
        
        if not user:
            return jsonify({'message': 'Anda belum melakukan reservasi.'}), 404
        else:
            # Fetch the most recent reservation for the user
            cur.execute("SELECT id, parkir_id, waktu_awal, waktu_akhir FROM reservasi WHERE user_id = %s ORDER BY waktu_awal DESC LIMIT 1", [user[0]])
            reservation = cur.fetchone()
            
            if reservation:
                reservation_id, reservation_parkir_id, waktu_awal, waktu_akhir = reservation
                
                # Check if the reservation is for the same parking lot
                if reservation_parkir_id != parkir_id:
                    return jsonify({'message': 'Reservasi tidak untuk tempat parkir ini.'}), 404
                
                # Check if the reservation is currently active
                current_time = datetime.datetime.now()
                if waktu_akhir and datetime.datetime.strptime(waktu_awal, '%Y-%m-%d %H:%M:%S') < current_time < datetime.datetime.strptime(waktu_akhir, '%Y-%m-%d %H:%M:%S'):
                    # Update reservation status to 'Active', update waktu_awal, and remove waktu_akhir
                    cur.execute("UPDATE reservasi SET status = 'Active', waktu_awal = %s, waktu_akhir = NULL WHERE id = %s", (current_time.strftime('%Y-%m-%d %H:%M:%S'), reservation_id))
                    mysql.connection.commit()
                    
                    event_name = "cancel_reservasi_" + str(reservation_id)
                    cur.execute("DROP EVENT IF EXISTS " + event_name)

                    return jsonify({'message': 'Check-in berhasil.'}), 200
                else:
                    return jsonify({'message': 'Anda belum melakukan reservasi atau reservasi Anda telah berakhir.'}), 404
            else:
                return jsonify({'message': 'Tidak ada reservasi ditemukan.'}), 404
    except Exception as e:
        return jsonify({'message': 'Terjadi kesalahan saat melakukan check-in.', 'error': str(e)}), 500

    

@app.route('/payment', methods=['POST'])
def payment():
    try:
        cur = mysql.connection.cursor()
        user_id = request.json['userId']
        
        # Mencari reservasi terbaru yang statusnya 'active' berdasarkan user_id
        cur.execute("SELECT * FROM reservasi WHERE user_id = %s AND status = 'Active' ORDER BY waktu_awal DESC LIMIT 1", [user_id])
        reservation = cur.fetchone()
        
        if not reservation:
            return jsonify({'message': 'Anda belum melakukan reservasi aktif.'}), 404
        else:
            waktu_awal = datetime.datetime.strptime(reservation[3], '%Y-%m-%d %H:%M:%S')
            waktu_akhir = datetime.datetime.now()
            selisih_waktu = waktu_akhir - waktu_awal
            total_detik = selisih_waktu.total_seconds()
            total_jam = int(total_detik // 3600)

            cur.execute("SELECT harga FROM tempat_parkir WHERE id = %s", [reservation[2]])
            harga_per_jam = cur.fetchone()[0]
            
            total_biaya = harga_per_jam + (total_jam * harga_per_jam)

            cur.execute("SELECT saldo FROM users WHERE id = %s", [user_id])
            saldo_pengguna = cur.fetchone()[0]
            if saldo_pengguna < total_biaya+harga_per_jam:
                return jsonify({'message': f'Saldo Anda harus {total_biaya} (biaya saat ini) + {harga_per_jam} (biaya satu jam ke depan)'}), 400
            
            cur.execute("UPDATE reservasi SET status = 'Checkout', waktu_akhir = %s WHERE id = %s", (waktu_akhir.strftime('%Y-%m-%d %H:%M:%S'), reservation[0]))
            mysql.connection.commit()
            waktu_revert = waktu_akhir + datetime.timedelta(minutes=10)
            cur.execute("CREATE EVENT IF NOT EXISTS revert_to_active_" + str(reservation[0]) + " ON SCHEDULE AT '" + waktu_revert.strftime('%Y-%m-%d %H:%M:%S') + "' DO BEGIN UPDATE reservasi SET status = 'Active', waktu_akhir = NULL WHERE id = " + str(reservation[0]) + "; UPDATE transaksi SET status = 'Canceled' WHERE reservasi_id = " + str(reservation[0]) + " AND status = 'Pending'; END")
            cur.execute("INSERT INTO transaksi (reservasi_id, status) VALUES (%s, %s)", (reservation[0], 'Pending'))
            mysql.connection.commit()

            return jsonify({'message': 'Pembayaran Berhasil, menunggu Anda keluar tempat parkir'}), 200
    except Exception as e:
        return jsonify({'message': 'An error occurred while making payment, ', 'error': str(e)}), 500

@app.route('/checkOut', methods=['POST'])
def check_out():
    try:
        cur = mysql.connection.cursor()
        plate_number = request.json['plateNumber']
        parkir_id = request.json['idParkir']
        
        cur.execute("SELECT id FROM users WHERE platenomor = %s", [plate_number])
        user = cur.fetchone()

        if not user:
            return jsonify({'message': 'Platnomor tidak ditemukan.'}), 404
        else:
            cur.execute("SELECT * FROM reservasi WHERE user_id = %s AND status = 'Checkout' ORDER BY waktu_awal DESC LIMIT 1", [user[0]])
            reservation = cur.fetchone()

            if reservation:
                reservation_parkir_id = reservation[2]

                if reservation_parkir_id != parkir_id:
                    return jsonify({'message': 'Reservasi tidak untuk tempat parkir ini.'}), 404
                
                cur.execute("SELECT total_biaya FROM transaksi WHERE reservasi_id = %s", [reservation[0]])
                total_biaya = cur.fetchone()[0]

                waktu_awal = datetime.datetime.strptime(reservation[3], '%Y-%m-%d %H:%M:%S')
                waktu_keluar = datetime.datetime.now()
                
                selisih_waktu = waktu_keluar - waktu_awal

                total_detik = selisih_waktu.total_seconds()
                total_jam = int(total_detik // 3600)
                sisa_detik = total_detik % 3600
                total_menit = int(sisa_detik // 60)

                if total_jam == 0:
                    lama_waktu = f"{total_menit} menit"
                else:
                    lama_waktu = f"{total_jam} jam {total_menit} menit"

                
                cur.execute("SELECT harga FROM tempat_parkir WHERE id = %s", [reservation[2]])
                harga_per_jam = cur.fetchone()[0]
                
                total_biaya = harga_per_jam + (total_jam * harga_per_jam)
                
                cur.execute("UPDATE reservasi SET waktu_akhir = %s, status = 'Finished' WHERE id = %s", (waktu_keluar.strftime('%Y-%m-%d %H:%M:%S'), reservation[0]))
                cur.execute("UPDATE transaksi SET lama_waktu = %s, total_biaya = %s, status = 'Done' WHERE reservasi_id = %s AND status = 'Pending'", [lama_waktu, total_biaya, reservation[0]])
                cur.execute("UPDATE users SET saldo = saldo - %s WHERE id = %s", [total_biaya, user[0]])
                cur.execute("DROP EVENT IF EXISTS revert_to_active_" + str(reservation[0]))
                cur.execute("UPDATE tempat_parkir SET tersedia = tersedia + 1 WHERE id = %s", [reservation[2]])
                mysql.connection.commit()

                return jsonify({'message': 'Check-out berhasil. Total biaya: {}'.format(total_biaya)}), 200
            else:
                return jsonify({'message': 'Anda belum melakukan pembayaran.'}), 404
        
    except Exception as e:
        return jsonify({'message': 'Terjadi kesalahan saat melakukan check-out.', 'error': str(e)}), 500
    

@app.route('/ongoing-reservations/<int:user_id>', methods=['GET'])
def ongoing_reservations(user_id):
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT r.id, r.waktu_awal, r.waktu_akhir, r.status, p.namatempat, p.alamat FROM reservasi r JOIN tempat_parkir p ON r.parkir_id = p.id WHERE r.user_id = %s AND r.status IN ('Pending', 'Active', 'Checkout')", [user_id])
        
        ongoing_reservations = cur.fetchall()
        
        if not ongoing_reservations:
            return jsonify({'message': 'Tidak ada reservasi aktif ditemukan untuk user_id tertentu.'}), 404
        
        active_reservation_list = []
        for reservation in ongoing_reservations:
            reservation_data = {
                'reservasi_id': reservation[0],
                'waktu_awal': reservation[1],
                'status': reservation[3],
                'nama_tempat_parkir': reservation[4],
                'alamat_tempat_parkir': reservation[5]
            }

            if reservation[3] == 'Pending':
                reservation_data['waktu_akhir'] = reservation[2]
            elif reservation[3] == 'Active':
                reservation_data['waktu_akhir'] = None
            elif reservation[3] == 'Checkout':
                waktu_baru = datetime.datetime.strptime(reservation[2], '%Y-%m-%d %H:%M:%S')
                waktu_baru = waktu_baru + datetime.timedelta(minutes=10)
                reservation_data['waktu_akhir'] = waktu_baru.strftime('%Y-%m-%d %H:%M:%S')
            
            active_reservation_list.append(reservation_data)
        
        return jsonify({'ongoing_reservations': active_reservation_list}), 200
    except Exception as e:
        return jsonify({'message': 'Terjadi kesalahan saat mengambil data reservasi aktif.', 'error': str(e)}), 500



@app.route('/finished-reservations/<int:user_id>', methods=['GET'])
def finished_reservations(user_id):
    try:
        cur = mysql.connection.cursor()
        
        cur.execute("""
            SELECT r.id, r.waktu_awal, r.waktu_akhir, r.status, p.namatempat, p.alamat
            FROM reservasi r
            JOIN tempat_parkir p ON r.parkir_id = p.id
            WHERE r.user_id = %s AND r.status IN ('Canceled', 'Finished')
            ORDER BY r.waktu_akhir DESC, r.id DESC
        """, [user_id])
        finished_reservations = cur.fetchall()
        
        if not finished_reservations:
            return jsonify({'message': 'Tidak ada reservasi selesai ditemukan untuk user_id tertentu.'}), 404
        
        finished_reservation_list = []
        for reservation in finished_reservations:
            reservation_data = {
                'reservasi_id': reservation[0],
                'waktu_awal': reservation[1],
                'waktu_akhir': reservation[2] if reservation[3] == 'Finished' else None,
                'status': reservation[3],
                'nama_tempat_parkir': reservation[4],
                'alamat_tempat_parkir': reservation[5]
            }

            if reservation[3] == 'Finished':
                # Fetch additional data from the transactions table
                cur.execute("SELECT * FROM transaksi WHERE reservasi_id = %s ORDER BY id DESC LIMIT 1", [reservation[0]])
                transaction_data = cur.fetchone()
                if transaction_data:
                    total_biaya_str = "{:,.0f}".format(transaction_data[3]).replace(',', '.')
                    reservation_data['lama_waktu'] = transaction_data[2]
                    reservation_data['total_biaya'] = total_biaya_str
                    reservation_data['transaction_status'] = transaction_data[4]

            finished_reservation_list.append(reservation_data)
        
        return jsonify({'finished_reservations': finished_reservation_list}), 200
    except Exception as e:
        return jsonify({'message': 'Terjadi kesalahan saat mengambil data reservasi selesai.', 'error': str(e)}), 500
    
@app.route('/topUp', methods=['POST'])
def top_up():
    try:
        cur = mysql.connection.cursor()
        id = request.json['transactionId']
        user_id = request.json['userId']
        amount = request.json['jumlah']
        status = request.json['status']

        cur.execute("INSERT INTO topup (id, user_id, jumlah, status, waktu) VALUES (%s, %s ,%s, %s, %s)", [id, user_id, int(amount),status, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
        mysql.connection.commit()

        cur.execute("SELECT status FROM topup WHERE id = %s", [id])
        result = cur.fetchone()
        if result and result[0] == 'success':
            cur.execute("UPDATE users SET saldo = saldo + %s WHERE id = %s", [amount, user_id])
            mysql.connection.commit()
            return jsonify({'message': 'Top-up telah berhasil.'}), 200
        else:
            return jsonify({'message': 'Top-up sedang diproses.'}), 200
    except Exception as e:
        return jsonify({'message': 'Terjadi kesalahan saat melakukan top-up.', 'error': str(e)}), 500



@app.route('/getStatusTransactionsMidtrans', methods=['POST'])
def getstatustransactionsmidtrans():
    try:
        data = request.get_json()

        transaction_id = data['transaction_id']
        status = data['transaction_status']
        amount = data['gross_amount']

        amount = float(amount)
        jumlah = int(amount)
                        
        if status == 'settlement':
            cur = mysql.connection.cursor()
            cur.execute("UPDATE topup SET status = 'success' WHERE id = %s", [transaction_id])
            cur.execute("UPDATE users SET saldo = saldo + %s WHERE id = (SELECT user_id FROM topup WHERE id = %s)", [jumlah, transaction_id])
            mysql.connection.commit()
            cur.close()
        elif status == 'expire' or status == 'cancel':
            cur = mysql.connection.cursor()
            cur.execute("UPDATE topup SET status = 'Failed' WHERE id = %s", [transaction_id])
            mysql.connection.commit()
            cur.close()
            
        return  jsonify({'message': 'Successfully'}), 200
    except Exception as e:
        return jsonify({'message': 'Terjadi kesalahan saat melakukan top-up', 'error': str(e)}), 500
    
@app.route('/getExpiredTime/<int:user_id>', methods=['GET'])
def get_expired_time(user_id):
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT waktu_akhir, status FROM reservasi WHERE user_id = %s AND (status = 'Pending' OR status = 'Checkout') ORDER BY waktu_awal DESC LIMIT 1", [user_id])
        row = cur.fetchone()
        
        if row:
            waktu, status = row
            
            if status == 'Pending':
                return jsonify({'waktu_akhir': waktu}), 200
            elif status == 'Checkout':
                waktu_baru = datetime.datetime.strptime(waktu, '%Y-%m-%d %H:%M:%S')
                waktu_baru = waktu_baru + datetime.timedelta(minutes=10)
                waktu_baru = waktu_baru.strftime('%Y-%m-%d %H:%M:%S')
                return jsonify({'waktu_akhir': waktu_baru}), 200
        return jsonify({'waktu_akhir': 'Reservasi tidak ditemukan.'}), 200
    
    except Exception as e:
        return jsonify({'message': 'Terjadi kesalahan saat mengambil waktu akhir reservasi.', 'error': str(e)}), 500
    

@app.route('/upload', methods=['POST'])
def upload_image():
    try:
        image = request.files['image']
        image.save('uploaded_image.jpg')
        return jsonify({'message': 'Gambar berhasil diunggah!'}), 200
    except Exception as e:
        return jsonify({'message': 'Terjadi kesalahan saat mengunggah gambar.', 'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)