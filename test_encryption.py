#!/usr/bin/env python3
"""Test script to verify encryption/decryption functionality."""

import sys
sys.path.insert(0, '/workspace')

from secure_messenger import encrypt_message, decrypt_message, generate_salt, derive_key

def test_encryption():
    print("=" * 60)
    print("Testing Encryption/Decryption")
    print("=" * 60)
    
    # Test 1: Basic encryption/decryption
    print("\n[Test 1] Basic encryption/decryption")
    message = "Hello, this is a secret message!"
    password = "test_password"
    salt = generate_salt()
    key = derive_key(password, salt)
    
    print(f"Original message: {message}")
    print(f"Password: {password}")
    print(f"Salt (hex): {salt.hex()[:32]}...")
    print(f"Key (hex): {key.hex()[:32]}...")
    
    encrypted = encrypt_message(message, key)
    print(f"\nEncrypted data:")
    print(f"  Nonce: {encrypted['nonce']}")
    print(f"  Ciphertext: {encrypted['ciphertext'][:50]}...")
    print(f"  Encrypted flag: {encrypted['encrypted']}")
    
    decrypted = decrypt_message(encrypted, key)
    print(f"\nDecrypted message: {decrypted}")
    
    if message == decrypted:
        print("✓ Test 1 PASSED: Message successfully encrypted and decrypted!")
    else:
        print("✗ Test 1 FAILED: Decrypted message doesn't match original!")
        return False
    
    # Test 2: Different keys produce different ciphertexts
    print("\n[Test 2] Different passwords produce different ciphertexts")
    salt2 = generate_salt()
    key2 = derive_key("different_password", salt2)
    encrypted2 = encrypt_message(message, key2)
    
    if encrypted['ciphertext'] != encrypted2['ciphertext']:
        print("✓ Test 2 PASSED: Different keys produce different ciphertexts!")
    else:
        print("✗ Test 2 FAILED: Ciphertexts should be different!")
        return False
    
    # Test 3: Wrong key fails decryption
    print("\n[Test 3] Wrong key fails decryption")
    try:
        wrong_decrypted = decrypt_message(encrypted, key2)
        print("✗ Test 3 FAILED: Should have failed with wrong key!")
        return False
    except Exception as e:
        print(f"✓ Test 3 PASSED: Correctly failed with wrong key: {type(e).__name__}")
    
    # Test 4: Long message
    print("\n[Test 4] Long message encryption")
    long_message = "A" * 1000
    encrypted_long = encrypt_message(long_message, key)
    decrypted_long = decrypt_message(encrypted_long, key)
    
    if long_message == decrypted_long:
        print("✓ Test 4 PASSED: Long message encrypted/decrypted successfully!")
    else:
        print("✗ Test 4 FAILED: Long message mismatch!")
        return False
    
    # Test 5: Unicode/special characters
    print("\n[Test 5] Unicode characters")
    unicode_message = "Привет мир! 🌍 Приветствие 你好 مرحبا"
    encrypted_unicode = encrypt_message(unicode_message, key)
    decrypted_unicode = decrypt_message(encrypted_unicode, key)
    
    if unicode_message == decrypted_unicode:
        print("✓ Test 5 PASSED: Unicode message encrypted/decrypted successfully!")
    else:
        print("✗ Test 5 FAILED: Unicode message mismatch!")
        return False
    
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED! ✓")
    print("=" * 60)
    return True

if __name__ == '__main__':
    success = test_encryption()
    sys.exit(0 if success else 1)
